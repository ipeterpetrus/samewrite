# Pra-registrasi ronde 3 — ditulis SEBELUM satu run pun dijalankan

Ditulis 2026-08-28. Ronde 1 dan 2 mentok langit-langit (plain 35/36 ROOT), jadi sisi
manfaat tak pernah teridentifikasi. Ronde 3 mencoba membuat RUANG-GAGAL. Supaya hasilnya
tak bisa kutarik ke mana pun sesudah melihat angkanya, aturannya dikunci di sini dulu.

## Prinsip fixture
Agen berhenti begitu uji TARGET hijau. Ruang-gagal karena itu menuntut dua hal sekaligus:
tambalan LOKAL di dekat gejala yang cukup membuat TARGET hijau, dan AKAR yang berjarak
beberapa lompatan di modul yang tidak diimpor langsung oleh modul gejala. Semua
deterministik — nol balapan, nol waktu, nol acak.

## Dua kontrol, dua-duanya sudah dijalankan (nol panggilan API)
- **Positif** — perbaikan AKAR: TARGET hijau DAN TETANGGA hijau. 5/5 lolos.
- **Negatif** — tambalan PINTAS: TARGET hijau DAN TETANGGA **merah**. 5/5 lolos.

`sort_group` DIBUANG sebelum pilot: pintasannya (mengurutkan string `"dept:name"`) setara
dengan perbaikan akar karena dept jadi prefiks, jadi fixture itu tak bisa membedakan apa pun.

## Fixture yang DIBEKUKAN (5)
`classvar_shared` · `flag_chain` · `pagination_edge` · `scale_table` · `swallow_deep`

## Pilot
Lengan `plain` saja, 3 ulangan x 5 fixture = 15 run. Haiku 4.5, config minimal, akun-2.

## Aturan seleksi — DIKUNCI SEBELUM MELIHAT HASIL
Sebuah fixture masuk A/B bila lengan **plain** GAGAL mencapai ROOT minimal sekali dari 3
ulangan (yakni ROOT-rate <= 2/3). Seleksi memakai **lengan kontrol saja**; memilih
berdasarkan selisih plain-vs-skill akan menjadi seleksi atas efek yang sedang diukur, dan
itu dilarang di sini.

Data pilot dipakai HANYA untuk seleksi. A/B memakai run BARU.

- >=1 fixture lolos -> A/B 2 lengan x 3 ulangan pada fixture yang lolos.
- 0 fixture lolos -> laporkan sebagai kegagalan KETIGA membangun ruang-gagal, dan
  **berhenti menyetel fixture ronde ini**. Tidak ada ronde 3b hasil utak-atik sesudah
  melihat kegagalan.

## Analisis yang dikunci
- Utama (hasil): McNemar berpasangan atas ROOT vs bukan-ROOT, dua-sisi.
- Sekunder (biaya): uji tanda berpasangan atas token per-run, dua-sisi, ties dibuang.
- Treatment wajib diverifikasi per-run: transkrip lengan `skill` HARUS memuat panggilan
  tool `Skill` untuk `systematic-debugging`; lengan `plain` harus nol.

## Penyimpangan protokol yang DIDEKLARASIKAN (ditulis sesudah pilot, sebelum A/B)
Pilot: `scale_table` SYMPTOM 3/3 (lolos), empat lainnya ROOT 3/3 (mentok). Hanya SATU
fixture yang lolos, jadi ulangan A/B dinaikkan **3 -> 6** per lengan.

Alasannya daya uji, bukan arah: dengan satu fixture, 3 pasang tak bisa mencapai signifikansi
apa pun (McNemar dua-sisi minimum p = 2/2^3 = 0,25), sementara 6 pasang bisa (2/2^6 = 0,031).
Keputusan ini diambil **sebelum satu pun run lengan `skill` dijalankan**, jadi tak bisa
dipilih berdasarkan hasil yang diinginkan.

Catatan jujur kedua: `scale_table` ada di **lantai** (0/3), bukan di pita 40-70% yang
disarankan panel. Lantai tetap sah untuk mendeteksi MANFAAT (kalau lengan skill naik, itu
sinyal), tapi ia tak bisa mendeteksi kerugian, dan satu fixture bukan sampel populasi bug.
