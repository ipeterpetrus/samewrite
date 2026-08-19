---
name: edit-discipline
description: Pilih Edit vs tulis-ulang-penuh saat menyunting berkas yang sudah ada; hindari penulisan nol-perubahan.
---

# Disiplin penyuntingan berkas

Dari ukuran, bukan selera: 24 transcript · 29.838 turn · 122 Write yang menimpa
berkas yang ditulis sendiri.

## Keputusan

| kondisi | pilih |
|---|---|
| berkas belum ada | Write |
| isi sama persis dengan yang di disk | **jangan tulis** — lanjut saja |
| perubahan terlokalisasi (≲3 blok) | **Edit / patch berjangkar** |
| perubahan tersebar, atau mayoritas isi berubah | **tulis ulang penuh** — sebut alasannya |

## Kenapa batas 3 blok, bukan "selalu Edit"

Rewrite di sampel rata-rata **6,9 blok perubahan**. Memaksa Edit untuk semuanya =
**+70% token** vs satu Write, karena tiap Edit membawa `old_string` berkonteks.
Hanya **43%** rewrite yang Edit-nya lebih murah.

Benchmark aider, model sama diuji dua format: `whole` mengungguli `diff` pada
**4 dari 6** pasangan — well-formed 100% vs 71,6–92,5%, malformed 0 vs 68–148.
Diff bukan kemenangan gratis; ia menukar token dengan risiko gagal-apply.

## Nol-perubahan

18 dari 122 penulisan (15%) isinya persis sama dengan yang sudah di disk —
terbesar 133 baris untuk nol perubahan. Hook `write_noop_guard.py` menegakkan ini
bila terpasang; aturan tetap berlaku untuk jalur di luar hook: `cat >` heredoc,
`tee`, `sed -i` yang menulis isi utuh.

## Proporsi

Seluruh halaman ini bernilai **~0,1% token sesi**. Input tumbuh **O(N²)** karena
transcript diputar ulang tiap turn; memotong panjang sesi memotong 50–88%.
Jangan mengira ini penggantinya.
