# Pra-registrasi ronde 4 — ditulis SEBELUM satu run pun dijalankan

## Hipotesis generator (disuling dari ronde 3, bukan dikarang)
Ronde 3: empat fixture mentok ROOT 3/3, satu (`scale_table`) SYMPTOM 3/3. Bedanya struktural,
bukan "lebih sulit":

> Cacat punya **N instans bersaudara** di dalam satu koleksi homogen. Uji TARGET menyebut
> **tepat satu**. Uji TETANGGA menguji saudara-saudaranya.

Kalau cacatnya TUNGGAL, memperbaiki instans = memperbaiki kelas, jadi pintasan dan akar
berimpit dan fixture tak bisa membedakan apa pun. Itulah empat fixture yang mentok.

**Prediksi yang bisa gagal:** kelima fixture ronde ini menghasilkan ruang-gagal (lengan
kontrol gagal ROOT minimal sekali dalam 3 ulangan). Kalau >=2 dari 5 justru ROOT 3/3,
hipotesis generatornya SALAH dan ditulis begitu — bukan dipereteli jadi "berlaku sebagian".

## Invarian tiap fixture (sudah diverifikasi mekanis, nol panggilan API)
koleksi >=12 entri · tepat 3 entri cacat · target menyebut 1 · tetangga menguji 2 sisanya
**dan** >=1 entri sehat · akar = satu suntingan memulihkan ketiganya · pintasan = memulihkan
yang disebut target saja.

Kontrol **positif** (akar -> target+tetangga hijau) dan **negatif** (pintasan -> target hijau,
tetangga MERAH): **5/5 memenuhi keduanya**.

## Lima fixture, lima substrat BERBEDA (supaya bukan satu fixture diuji lima kali)
`scale_table` baris tabel data · `config_keys` nilai konfigurasi salah-parse ·
`sibling_callers` helper bersama tanpa penjaga, 4 situs pemanggil · `subclass_family` cacat
kelas dasar diwarisi 4 subclass · `handler_registry` bug tersalin di 3 dari 12 handler.

## Pilot
Lengan kontrol saja, 3 ulangan x 5 fixture = 15 run. Haiku 4.5, config minimal, akun-2.

## Aturan seleksi — DIKUNCI SEBELUM MELIHAT HASIL
Fixture masuk A/B bila lengan **kontrol** gagal ROOT >=1x dari 3. Seleksi memakai lengan
kontrol SAJA. Data pilot hanya untuk seleksi; A/B memakai run baru.

## A/B
4 ulangan x 2 lengan pada setiap fixture yang lolos.

## Analisis yang dikunci
- Utama: McNemar berpasangan atas ROOT vs bukan-ROOT, **digabung lintas fixture**, dua-sisi.
  Penggabungan sah karena kelima fixture adalah instans dari SATU generator yang
  dispesifikasikan di atas sebelum data ada; hasil per-fixture tetap dilaporkan terpisah.
- Sekunder: uji tanda berpasangan atas token per-run, dua-sisi, ties dibuang.
- Treatment wajib diverifikasi per-run (lengan skill harus memuat panggilan tool `Skill`;
  lengan kontrol harus nol).

## Yang TIDAK diklaim
Satu model (Haiku 4.5). Kelima fixture ditulis penulis yang sama sesudah melihat ronde 3 —
ini uji hipotesis generator, bukan replikasi independen.

## HASIL PILOT — prediksi pra-registrasi GAGAL (dicatat apa adanya)
`scale_table` SYMPTOM 3/3 · `handler_registry` SYMPTOM 3/3 · `sibling_callers` SYMPTOM 3/3 ·
**`config_keys` ROOT 3/3** · **`subclass_family` ROOT 3/3**.

Ambang falsifikasi yang kutulis sendiri (">=2 dari 5 mentok -> hipotesis SALAH") **menembak**.
Struktur instans-bersaudara karena itu **perlu tapi tidak cukup**. A/B tetap jalan pada 3
fixture yang lolos, sesuai aturan seleksi.

**Hipotesis POST-HOC (untuk ronde berikut, BUKAN temuan ronde ini):** dua yang tak menjebak
punya akar yang duduk **di jalur baca minimal** dari kegagalan — `as_bool()` dan
`Shape.name` mustahil tidak dibaca saat menelusuri galatnya, dan begitu dibaca, salahnya
kelihatan. Tiga yang menjebak menaruh akarnya **di luar** jalur itu: satu baris di tabel 40
baris, satu dari 12 fungsi hampir-kembar, dan sebuah helper yang pemanggil-lainnya tak
terlihat dari jalur gagal. Ini dugaan sesudah melihat data; harus diuji terpisah.
