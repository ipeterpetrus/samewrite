#!/usr/bin/env python3
"""Uji tools/carry.py: rumus carry, atribusi tool_result, gerbang --min-turns,
dan janji privasinya. Berdiri sendiri — jalankan berkas ini, tanpa runner."""
import json, os, subprocess, sys, tempfile, time as _time

CARRY = os.path.join(os.path.dirname(__file__), "..", "tools", "carry.py")
sys.path.insert(0, os.path.dirname(CARRY))
import carry  # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


def turn(text=None, tool=None, tool_id=None, inp=None):
    c = []
    if text is not None:
        c.append({"type": "text", "text": text})
    if tool:
        c.append({"type": "tool_use", "id": tool_id, "name": tool, "input": inp or {}})
    return json.dumps({"type": "assistant",
                       "message": {"usage": {"output_tokens": 1}, "content": c}})


def result(tool_id, body):
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": body}]}})


def write(d, name, lines):
    p = os.path.join(d, name)
    open(p, "w").write("\n".join(lines) + "\n")
    return p


def main():
    with tempfile.TemporaryDirectory() as d:
        # 3 turn. prose "x"*10 di turn 1 -> carry 10*(3-1)=20. prose di turn 3 -> 0.
        p = write(d, "s.jsonl", [
            turn("x" * 10),
            turn(tool="Bash", tool_id="t1", inp={"command": "y" * 4}),
            result("t1", "z" * 100),
            turn("q" * 7),
        ])
        N, items, usage = carry.scan(p)
        check("turn dihitung dari usage", N, 3)
        check("prose turn 1 -> carry = ukuran x sisa turn",
              max(n * (N - i) for (i, n, s) in items if s == "prose"), 10 * 2)
        check("tool_result diatribusikan ke nama tool-nya",
              any(s == "result:Bash" for _, _, s in items), True)
        check("hasil Bash tiba di turn 2 -> carry = 100 x 1",
              [n * (N - i) for (i, n, s) in items if s == "result:Bash"], [100])
        check("prose turn terakhir -> carry nol",
              sorted(n * (N - i) for (i, n, s) in items if s == "prose"), [0, 20])

        check("bucket: panggilan dan hasil Bash menyatu",
              (carry.bucket("call:Bash"), carry.bucket("result:Bash")), ("Bash", "Bash"))
        check("bucket: Write dan Edit satu ember",
              (carry.bucket("call:Write"), carry.bucket("call:Edit")), ("Write/Edit", "Write/Edit"))
        check("bucket: attachment tetap terpisah per jenis",
              carry.bucket("attach:skill_listing"), "attach:skill_listing")
        check("bucket: tool lain tak mencemari ember bernama",
              carry.bucket("call:Grep"), "other tools")

        # --min-turns membuang sesi pendek: sesi ini 3 turn, ambang 50 -> nol
        a = carry.accumulate([p], min_turns=50)
        check("--min-turns membuang sesi pendek", a["sessions"], 0)
        check("nol sesi -> keluaran jujur, bukan pembagian nol",
              carry.render(a).strip(),
              "no carry to report: 0 session(s) read (1 below --min-turns, 0 unreadable). "
              "A session whose every item lands on its final turn carries nothing.")

        a = carry.accumulate([p], min_turns=1)
        check("ambang rendah -> sesi terhitung", (a["sessions"], a["turns"]), (1, 3))

        # attachment (banner hook) dihitung, dan dihitung di turn tempat ia disuntikkan
        p2 = write(d, "a.jsonl", [
            json.dumps({"type": "attachment",
                        "attachment": {"type": "skill_listing", "content": "s" * 50}}),
            turn("hai"),
            turn("lagi"),
        ])
        a2 = carry.accumulate([p2], min_turns=1)
        check("banner turn 0 -> carry = ukuran x seluruh sesi",
              a2["carry"]["attach:skill_listing"], 50 * 2)

        # privasi: keluaran tak boleh memuat path, nama berkas, atau isi
        out = subprocess.run([sys.executable, CARRY, p, p2, "--min-turns", "1"],
                             capture_output=True, text=True).stdout
        check("keluaran tak memuat path", d in out, False)
        check("keluaran tak memuat isi tool", "zzz" in out, False)
        check("keluaran memuat ember Bash", "Bash" in out, True)

        # markdown: tabel valid, persentase menjumlah ~100
        md = subprocess.run([sys.executable, CARRY, p, "--markdown", "--min-turns", "1"],
                            capture_output=True, text=True).stdout
        # HANYA tabel "Carry by source": dokumen kini memuat tabel lain yang juga
        # berbaris "| `...`" (per-turn berharga) dan kolom-2-nya BUKAN persen.
        # Memindai seluruh dokumen membuat tes ini menuduh tabel yang tak bersalah.
        body = md.split("## Carry by source", 1)[1]
        pct = [float(x.split("|")[2].strip().rstrip("%")) for x in body.splitlines()
               if x.startswith("| `")]
        check("markdown: persentase carry menjumlah 100", round(sum(pct)), 100)

        # Kolom carry utama WAJIB byte mentah, bukan token hasil konversi diam-diam.
        # Konstanta byte->token bergantung bahasa (3,31 EN vs 1,98 ID di korpus penulis),
        # jadi menerapkannya tanpa diminta membuat setiap angka bergerak bersama.
        txt = subprocess.run([sys.executable, CARRY, p, "--min-turns", "1"],
                             capture_output=True, text=True).stdout
        check("header carry memakai byte", "carry_B" in txt and "carry_bytes=" in txt, True)
        check("nol kolom token tanpa --b2t", "carry_tok" in txt, False)
        # kolom-2 adalah %carry: parser posisional lama (int di field-2) HARUS melempar
        try:
            int([x.split()[1] for x in txt.splitlines() if x.startswith("Bash ")][0])
            check("parser posisional lama gagal keras", False, True)
        except (ValueError, IndexError):
            check("parser posisional lama gagal keras", True, True)
        raw = [int(x.split()[2].replace(",", "")) for x in txt.splitlines()
               if x.startswith("Bash ")]
        tok = subprocess.run([sys.executable, CARRY, p, "--min-turns", "1", "--b2t", "2"],
                             capture_output=True, text=True).stdout
        check("--b2t memunculkan kolom token", "carry_tok" in tok, True)

        # --history: observer yang menyimpan riwayat harus (a) menulis record, (b) pada run
        # berikutnya melaporkan PERUBAHAN, dan (c) tak pernah menulis path/isi ke ledger.
        hp = os.path.join(d, "hist.jsonl")
        h1 = subprocess.run([sys.executable, CARRY, p, "--min-turns", "1", "--history", hp],
                            capture_output=True, text=True).stdout
        check("history: run pertama bilang first record", "first record" in h1, True)
        h2 = subprocess.run([sys.executable, CARRY, p, "--min-turns", "1", "--history", hp],
                            capture_output=True, text=True).stdout
        check("history: run kedua melapor sejak-run-terakhir", "since last run" in h2, True)
        hraw = open(hp, encoding="utf-8").read()
        # Bukan cuma path fixture: NOL path absolut apa pun. Uji mutasi membuktikan versi
        # pertama cek ini lolos saat cwd yang bocor, karena cwd != direktori fixture.
        check("history tak memuat path fixture", d in hraw, False)
        check("history tak memuat path absolut apa pun", "/home/" in hraw or "/tmp/" in hraw, False)
        check("history tak memuat isi tool", "zzz" in hraw, False)
        check("history memuat share", '"shares"' in hraw, True)
        # Delta hanya sah kalau korpusnya sebanding. Run atas 1 berkas lalu 2 berkas
        # BUKAN pergerakan; tanpa cek ini ia dilaporkan seolah-olah pergerakan.
        hp2 = os.path.join(d, "hist2.jsonl")
        subprocess.run([sys.executable, CARRY, p, "--min-turns", "1", "--history", hp2],
                       capture_output=True, text=True)
        h3 = subprocess.run([sys.executable, CARRY, p, p2, "--min-turns", "1",
                             "--history", hp2], capture_output=True, text=True).stdout
        check("korpus berubah -> delta DITOLAK", "corpus changed" in h3, True)
        check("korpus berubah -> nol angka delta palsu", "since last run" in h3, False)

        # Rotasi log: jumlah BERKAS berubah, isi tidak. Delta harus tetap dilaporkan —
        # kriteria sebanding adalah turn, bukan berapa berkas isinya dipecah.
        hp4 = os.path.join(d, "hist4.jsonl")
        rot = {"ts": int(_time.time()) - 3600, "sessions": 1, "turns": 3,
               "carry_bytes": 999, "scanned": 1,
               "shares": {"Bash": 60.0, "prose": 40.0}, "bpt": {"Bash": 9, "prose": 9}}
        open(hp4, "w").write(json.dumps(rot) + "\n")
        h4 = subprocess.run([sys.executable, CARRY, p, "--min-turns", "1", "--history", hp4],
                            capture_output=True, text=True).stdout
        check("rotasi berkas tak menolak delta", "corpus changed" in h4, False)

        # Jam mundur: record dgn ts lebih tua ditulis belakangan -> JANGAN lapor delta.
        hp5 = os.path.join(d, "hist5.jsonl")
        fut = dict(rot, ts=int(_time.time()) + 86400)
        open(hp5, "w").write(json.dumps(fut) + "\n")
        h5 = subprocess.run([sys.executable, CARRY, p, "--min-turns", "1", "--history", hp5],
                            capture_output=True, text=True).stdout
        check("jam mundur -> delta ditolak", "clock went backwards" in h5, True)

        # TREN: arah jangka panjang butuh SELURUH berkas, bukan dua titik terakhir, dan
        # tak boleh diklaim dari sampel kecil. Slope diuji terhadap kemiringan yang dibuat.
        import time as _t
        base = int(_t.time()) - 60 * 86400
        recs = []
        for i in range(6):
            recs.append({"ts": base + i * 12 * 86400, "sessions": 10, "turns": 1000 + i * 100,
                         "carry_bytes": 10 ** 6, "scanned": 100,
                         "shares": {"Bash": 50 + i * 1.5, "Read": 30 - i * 1.0},
                         "bpt": {"Bash": 100, "Read": 100}})
        t = carry.trend(recs, "Bash")
        check("trend: slope per hari benar", round(t["slope"] * 30, 2), 3.75)
        check("trend: n dihitung", t["n"], 6)
        check("trend: <4 record tak mengklaim arah", carry.trend(recs[:3], "Bash"), None)
        # outlier: nilai terakhir jauh dari kebiasaan
        flat = [{"ts": base + i * 86400, "shares": {"X": 10.0}} for i in range(6)]
        flat.append({"ts": base + 7 * 86400, "shares": {"X": 25.0}})
        to = carry.trend(flat, "X")
        check("trend: lonjakan terakhir terbaca sebagai outlier", abs(to["z"]) >= 2.0, True)
        rawtok = [int(x.split()[-1].replace(",", "")) for x in tok.splitlines()
                  if x.startswith("Bash ")]
        if raw and rawtok:
            check("kolom byte bukan kolom token", raw[0] != rawtok[0], True)
            check("token = byte / b2t", abs(rawtok[0] - raw[0] / 2) <= 1, True)

        # berkas rusak tak boleh menjatuhkan alat (fail-open seperti guard)
        bad = os.path.join(d, "bad.jsonl")
        open(bad, "w").write("{ini bukan json\n" + turn("ok") + "\n")
        Nb, _, _ = carry.scan(bad)
        check("baris rusak dilewati, bukan crash", Nb, 1)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
