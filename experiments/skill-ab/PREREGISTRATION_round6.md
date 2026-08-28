# Pra-registrasi ronde 6 — ditulis SEBELUM satu run pun dijalankan

## Hipotesis ketiga (dua sebelumnya sudah mati oleh ambangnya sendiri)
Ronde 4 membunuh "instans bersaudara". Ronde 5 membunuh "helper bersama" (1 dari 6). Dugaan
post-hoc ronde 5: lima yang tak menjebak punya pemanggil **penerus murni** — tak ada apa pun
untuk dijaga di sana, jadi satu-satunya tempat menyunting memang helper. Yang menjebak punya
pemanggil yang memegang parameternya sendiri.

> **Ruang-gagal muncul bila PEMANGGIL punya sesuatu yang wajar dijaga di tempatnya.**

Enam fixture, enam alasan berbeda kenapa penjagaan lokal terasa wajar: parameter ber-default ·
ukuran halaman ber-default · argumen yang DIHITUNG pemanggil · pemanggil yang SUDAH punya
pra-cek · pemanggil yang SUDAH punya try/except · flag mode yang dipegang pemanggil.

Tiga kontrol mekanis LULUS 6/6 (pra merah · akar → target+tetangga+holdout hijau · pintasan →
target hijau, holdout MERAH).

## Prediksi yang bisa gagal
>=4 dari 6 menghasilkan ruang-gagal (kontrol gagal ROOT >=1x dari 3). Bila <4, hipotesis
ketiga SALAH dan ditulis salah.

## ATURAN BERHENTI PROGRAM — ditulis sekarang, bukan sesudah kecewa
Bila ronde 6 juga <4, **berhenti membangun generator**. Kesimpulan program ditulis apa adanya:
ruang-gagal itu jarang dan aku gagal memprediksinya dari struktur tiga kali berturut-turut;
keluaran yang bertahan adalah pengukuran BIAYA dan METODE-nya (tiga oracle, lengan placebo,
audit asal-perbaikan, pra-registrasi ber-ambang), bukan teori tentang bug apa yang menjebak.
Panel adv-max sudah memperingatkan risiko "lumpuh karena terus merancang ulang"; aturan ini
yang membatasinya.

## Lengan & analisis (sama seperti ronde 5)
`plain` · `placebo` (ketelitian+perencanaan, tanpa kata akar/kelas) · `skill`.
Efek skill dihitung HANYA bila `skill` > `placebo`. Primer PER-FIKSTUR (binomial eksak
dua-sisi); gabungan hanya sensitivitas. Tiap ROOT wajib lolos audit asal-perbaikan. Treatment
diverifikasi per-run.

## Yang TIDAK diklaim
Satu model (Haiku 4.5); enam stimulus tetap berkorelasi satu penulis; estimand bukan populasi
bug. Placebo bukan inert — ini banding dua treatment, bukan treatment lawan nihil.

## HASIL PILOT — prediksi TEPAT untuk pertama kalinya
`truncate_guard` 0/3 · `caller_try` 0/3 · `existing_precheck` 1/3 · `caller_computes` 2/3 →
**4 dari 6 punya ruang-gagal** (ambang >=4 terlewati). Yang mentok: `mode_flag` 3/3 dan
`page_size` 3/3.

Dua di antaranya (`existing_precheck` 1/3, `caller_computes` 2/3) jatuh di pita 33-67% yang
panel adv-max sebut paling informatif — bukan lantai, bukan langit-langit. A/B lanjut pada
keempatnya, 3 lengan x 4 ulangan, sesuai aturan yang sudah dikunci.

## PENURUNAN STATUS — ditulis sesudah panel adv-max, sebelum A/B selesai
Panel memvonis premis P2 **PATAH**: "wajar dijaga di tempatnya" bisa berarti tak lebih dari
"model mengambil pintasan" — outcome mendefinisikan sebabnya kecuali fiturnya dikunci sebagai
predikat mekanis pra-run (nilai ada di scope pemanggil · tanpa impor baru · kontrak terjaga ·
tambalan <= N baris), dilabeli buta sebelum lengan dijalankan. Fixture-ku dilabeli oleh
ALASAN struktural yang kutulis sebelum menjalankan apa pun, tapi TIDAK diformalkan jadi
predikat yang bisa dicek mesin. Karena itu:

**Ronde 6 diturunkan dari KONFIRMATORI menjadi EKSPLORATORI TERAKHIR YANG DIBEKUKAN.**
Tak ada generator ke-4, apa pun hasilnya. Tiga hal lain yang panel patahkan dan kucatat
sebagai batas, bukan kubantah: (a) pra-registrasi per-ronde melindungi tiap ronde, BUKAN
urutannya — ini hipotesis ketiga di harness yang sama, p per-ronde tidak dikoreksi
family-wise; (b) placebo-ku cocok PANJANG, bukan BENTUK INTERAKSI (skill mewajibkan alur
berfase, placebo tidak), jadi "skill vs placebo" masih mencampur isi-skill dengan
alur-yang-diwajibkan; (c) enam fixture berpermukaan beda bisa isomorfik di mata harness,
sehingga N efektifnya lebih kecil dari 6.

Tiga serangan panel DIBUNUH hakimnya sendiri: tuduhan p-hacking (program ini menerbitkan dua
generator yang gagal sebagai gagal), usul "berhenti sebelum ronde 6" (aturan berhenti menyala
SESUDAH gagal, menghentikannya lebih awal justru post-hoc), dan usul menahan log mentah
(publikasi justru menuntut artefaknya).
