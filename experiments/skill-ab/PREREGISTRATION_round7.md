# Pra-registrasi ronde 7 — dua skill yang BENAR-BENAR selalu menyala

Enam ronde sebelumnya menguji `systematic-debugging`: **nol invokasi** dalam 1.409 transcript.
`caveman` (4.664 B) dan `ponytail` (5.228 B) disuntik **tiap sesi** lewat hook SessionStart.
Mereka yang membayar carry tiap turn, jadi mereka yang layak diuji.

## Perlakuan
Banner asli diekstrak dari transcript nyata dan disuntik lewat hook SessionStart di config
sementara — **bentuk yang sama dengan produksi**, terlihat di transcript sehingga bisa
diverifikasi, bukan diasumsikan. Lengan: `plain` · `oneline` (placebo satu kalimat) · `mode`
(banner penuh). Pertanyaan intinya sama seperti ronde 5-6: **apakah 4-5 kB aturan mengalahkan
satu kalimat?**

## caveman — klaim "-65% token keluaran, seluruh substansi teknis tetap"
Tugas MENJELASKAN (4 bug, agen dilarang menyunting). Dua ukuran, keduanya mekanis:
- **utama** jumlah kata jawaban, berpasangan per (fixture, ulangan);
- **gerbang substansi** cakupan fakta wajib via regex (nama fungsi, operator, konsep).
  Ringkas tapi kehilangan fakta = GAGAL, bukan hemat.

**Prediksi yang bisa gagal:** pengurangan kata lengan `mode` vs `plain` **>=50%**. Klaimnya
65%; bila terukur <50%, klaim itu berlebihan pada kelas tugas ini dan ditulis begitu.

## ponytail — klaim "diff terpendek yang bekerja, tanpa abstraksi tak diminta"
Tugas MENGIMPLEMENTASI (4 permintaan kecil yang menggoda untuk di-over-engineer).
- **gerbang** pytest hijau (perubahan yang tak bekerja tidak dihitung "pendek");
- **utama** baris bertambah di `mod.py`;
- **sekunder** def/class baru (AST) dan berkas baru.

**Prediksi yang bisa gagal:** `mode` < `plain` pada baris bertambah di **>=3 dari 4** fixture.

## Yang TIDAK diklaim
Satu model (Haiku 4.5), tugas kecil, satu penulis fixture. Estimand = benchmark ini.
Placebo cocok NIAT, bukan bentuk interaksi — batas yang sama seperti ronde 5-6.
