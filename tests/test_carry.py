#!/usr/bin/env python3
"""Uji tools/carry.py: rumus carry, atribusi tool_result, gerbang --min-turns,
dan janji privasinya. Berdiri sendiri — jalankan berkas ini, tanpa runner."""
import json, os, subprocess, sys, tempfile

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
              carry.render(a).strip(), "no session met --min-turns")

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
        pct = [float(x.split("|")[2].strip().rstrip("%")) for x in md.splitlines()
               if x.startswith("| `")]
        check("markdown: persentase carry menjumlah 100", round(sum(pct)), 100)

        # berkas rusak tak boleh menjatuhkan alat (fail-open seperti guard)
        bad = os.path.join(d, "bad.jsonl")
        open(bad, "w").write("{ini bukan json\n" + turn("ok") + "\n")
        Nb, _, _ = carry.scan(bad)
        check("baris rusak dilewati, bukan crash", Nb, 1)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
