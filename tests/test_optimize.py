#!/usr/bin/env python3
"""Uji tools/optimize.py: ambang beku, penolakan data rusak, kebijakan TAK PERNAH dimutasi,
dan janji privasinya — kenari rahasia ditanam di transcript + ledger, lalu dibuktikan absen dari
setiap keluaran. Berdiri sendiri — jalankan berkas ini, tanpa runner."""
import collections, hashlib, json, os, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPT = os.path.join(ROOT, "tools", "optimize.py")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import optimize  # noqa: E402

P = F = 0
CANARY = "SAMEWRITE_CANARY_SECRET_DO_NOT_LEAK_7f83a1c9"
EMPTY_HIST = {"comparable": [], "total": 0, "in_scope": 0, "rejected": {}, "dropped": [],
              "time_order": "ok"}


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


def rec(ts, shares, turns=1000, sessions=40, **kw):
    r = {"schema_version": 1, "record_type": "carry_run", "ts": ts, "sessions": sessions,
         "turns": turns, "carry_bytes": 10 ** 7, "scanned": 100,
         "shares": shares, "bpt": {k: 1.0 for k in shares}}
    r.update(kw)
    return r


def write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    return path


def run(args):
    p = subprocess.run([sys.executable, OPT] + args, capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout + p.stderr


def main():
    d = tempfile.mkdtemp(prefix="sw-opt-")
    empty = os.path.join(d, "none.jsonl")

    # ---------------------------------------------------------------- validation / corruption
    cases = [
        ("record ok", rec(1, {"Bash": 50.0, "Read": 50.0}), True),
        ("bukan objek", [1, 2, 3], False),
        ("share negatif", rec(1, {"Bash": -5.0, "Read": 105.0}), False),
        ("share tak berjumlah 100", rec(1, {"Bash": 10.0, "Read": 10.0}), False),
        ("share bukan angka", rec(1, {"Bash": "50", "Read": 50.0}), False),
        ("bilangan raksasa", rec(1, {"Bash": 50.0, "Read": 50.0}, turns=10 ** 18), False),
        ("turns negatif", rec(1, {"Bash": 50.0, "Read": 50.0}, turns=-5), False),
        ("schema tak dikenal", dict(rec(1, {"Bash": 50.0, "Read": 50.0}), schema_version=99), False),
        ("record_type asing", dict(rec(1, {"Bash": 50.0, "Read": 50.0}), record_type="telemetry"), False),
        ("tanpa shares", {"schema_version": 1, "ts": 1}, False),
        ("schema 0 (record lama) diterima", {"ts": 1, "turns": 900, "shares": {"Bash": 100.0}}, True),
        ("field asing diabaikan, bukan ditolak",
         dict(rec(1, {"Bash": 50.0, "Read": 50.0}), future_field={"x": 1}), True),
    ]
    for label, obj, want in cases:
        check(f"valid_record: {label}", optimize.valid_record(obj)[0], want)

    p = write(os.path.join(d, "corrupt.jsonl"),
              [rec(100, {"Bash": 50.0, "Read": 50.0}, run_id="a" * 32), "{tidak lengkap", "", "null",
               rec(100, {"Bash": 50.0, "Read": 50.0}, run_id="a" * 32)])     # penulisan ULANG run yang sama
    recs, rejected, lines = optimize.load_history(p)
    check("JSONL rusak: satu record sah bertahan", len(recs), 1)
    check("baris tak terparse dihitung", rejected["unparseable line"], 1)
    check("run_id sama (retry) dihitung sekali", rejected["duplicate run_id (retry)"], 1)
    # Dua AGEN boleh menghasilkan metrik identik. Tanpa run_id itu dua pengamatan, bukan duplikat:
    # membuang salah satunya akan mengecilkan populasi yang sedang diukur.
    p2 = write(os.path.join(d, "twin.jsonl"),
               [rec(100, {"Bash": 50.0, "Read": 50.0}, run_id="b" * 32),
                rec(100, {"Bash": 50.0, "Read": 50.0}, run_id="c" * 32)])
    check("metrik identik dari dua run BERBEDA tetap dua record", len(optimize.load_history(p2)[0]), 2)
    check("berkas tak ada -> nol record, tanpa exception", optimize.load_history(empty)[0], [])

    # ---------------------------------------------------------------- comparability & clock
    p = write(os.path.join(d, "shrink.jsonl"),
              [rec(100, {"Bash": 40.0, "Read": 60.0}, turns=10000),
               rec(200, {"Bash": 60.0, "Read": 40.0}, turns=1000)])
    recs, _, _ = optimize.load_history(p)
    keep, dropped = optimize.comparable(recs)
    check("korpus menyusut 10x -> record lama TIDAK dibandingkan", (len(keep), len(dropped)), (1, 1))
    check("jam mundur terdeteksi",
          optimize.time_order([rec(200, {"Bash": 100.0}), rec(100, {"Bash": 100.0})]), "reversed")
    check("jam maju: ok",
          optimize.time_order([rec(100, {"Bash": 100.0}), rec(200, {"Bash": 100.0})]), "ok")
    check("stempel waktu identik -> ambigu, bukan tren",
          optimize.time_order([rec(100, {"Bash": 100.0}), rec(100, {"Bash": 90.0, "Read": 10.0})]),
          "ambiguous")

    rows = [rec(100 + i * 86400, {"Bash": 30.0 + i * 5, "Read": 70.0 - i * 5},
                turns=1000 * (10 if i == 0 else 1)) for i in range(5)]
    p = write(os.path.join(d, "trend.jsonl"), rows)
    rc, out = run(["--history", p, "--ledger", empty, "--scan"])
    check("record tak sebanding dilaporkan, bukan dipakai diam-diam", "not comparable" in out, True)

    # ---------------------------------------------------------------- thresholds
    flat = [rec(100 + i * 86400, {"Bash": 40.0, "Read": 60.0}) for i in range(6)]
    p = write(os.path.join(d, "flat.jsonl"), flat)
    rc, out = run(["--history", p, "--ledger", empty, "--scan"])
    check("6 record datar -> nol kandidat tren", "NO_ACTION" in out, True)
    rising = [rec(100 + i * 86400 * 7, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8}) for i in range(6)]
    p = write(os.path.join(d, "rise.jsonl"), rising)
    rc, out = run(["--history", p, "--ledger", empty, "--scan"])
    check("kenaikan kuat -> kandidat tren", "trend-bash" in out, True)
    check("kandidat tren menyebut pp/bulan", "pp/month" in out, True)

    led = write(os.path.join(d, "led_small.jsonl"),
                [{"ts": 1, "host": "h", "event": "checked", "bytes": 10} for _ in range(20)])
    rc, out = run(["--history", empty, "--ledger", led, "--scan"])
    check("ledger kecil -> OBSERVED, bukan kandidat", "field sample is too small" in out, True)
    led = write(os.path.join(d, "led_dead.jsonl"),
                [{"ts": 1, "host": "h", "event": "checked", "bytes": 10} for _ in range(200)])
    rc, out = run(["--history", empty, "--ledger", led, "--scan"])
    check("ledger besar dgn nol deny -> kandidat PENSIUN aturan", "noop-guard-retire" in out, True)
    led = write(os.path.join(d, "led_live.jsonl"),
                [{"ts": 1, "host": "h", "event": "checked", "bytes": 10} for _ in range(180)] +
                [{"ts": 1, "host": "h", "event": "denied", "bytes": 10} for _ in range(20)])
    rc, out = run(["--history", empty, "--ledger", led, "--scan"])
    check("ledger dgn deny 10% -> guard masih membayar", "noop-guard-retain" in out, True)

    # ---------------------------------------------------------------- population: host & model
    shifted = [rec(100, {"Bash": 30.0, "Read": 70.0}, runtimes={"2.1.200": 5}, models={"m1": 5}),
               rec(100 + 86400, {"Bash": 45.0, "Read": 55.0}, runtimes={"2.1.270": 5}, models={"m1": 5})]
    pop = optimize.population(shifted)
    check("versi runtime berubah + pergeseran besar -> HOST_BEHAVIOR_SHIFT", bool(pop["host_shift"]), True)
    same = [rec(100, {"Bash": 30.0, "Read": 70.0}, runtimes={"2.1.270": 5}, models={"m1": 5}),
            rec(100 + 86400, {"Bash": 31.0, "Read": 69.0}, runtimes={"2.1.270": 5}, models={"m1": 5})]
    check("runtime sama -> nol shift", bool(optimize.population(same)["host_shift"]), False)
    check("satu model, sesi cukup -> GLOBAL_SIGNAL", optimize.population(same)["segmentation"], "GLOBAL_SIGNAL")
    multi = [rec(100, {"Bash": 50.0, "Read": 50.0}, sessions=5, models={"m1": 3, "m2": 3})]
    check("dua model, sesi sedikit -> INSUFFICIENT_DATA", optimize.population(multi)["segmentation"], "INSUFFICIENT_DATA")

    # ---------------------------------------------------------------- konsentrasi butuh korpus
    live_small = {"sessions": 3, "turns": 100, "carry": collections.Counter({"Bash": 90, "Read": 10}),
                  "scanned": 3, "short": 0}
    f = optimize.analyse(live_small, EMPTY_HIST, None, None)
    check("3 sesi: Bash 90% tetap OBSERVED (di bawah lantai)", [x["state"] for x in f], ["OBSERVED"])
    live_big = {"sessions": 40, "turns": 2000, "carry": collections.Counter({"Bash": 90, "Read": 10}),
                "scanned": 40, "short": 0}
    f = optimize.analyse(live_big, EMPTY_HIST, None, None)
    check("40 sesi: Bash 90% -> CANDIDATE", f[0]["state"], "CANDIDATE")
    check("kandidat membawa gerbang anggaran instruksi", f[0]["always_on_bytes_delta"], 0)

    # ---------------------------------------------------------------- privasi: kenari
    prof = os.path.join(d, "profile", "projects", "-repo")
    os.makedirs(prof)
    tp = os.path.join(prof, "s.jsonl")
    rows = [{"type": "attachment", "attachment": {"type": "skill_listing",
             "content": "- alpha: does a thing\n- beta: " + CANARY + " never invoked\n"}}]
    for i in range(60):
        rows.append({"type": "assistant", "version": "2.1.270",
                     "message": {"model": "claude-x", "usage": {"input_tokens": 1, "output_tokens": 1},
                                 "content": [{"type": "tool_use", "id": str(i), "name": "Bash",
                                              "input": {"command": "echo " + CANARY}}]}})
        rows.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": str(i),
                                                              "content": CANARY * 20}]}})
    write(tp, rows)
    led = write(os.path.join(d, "led_canary.jsonl"),
                [{"ts": 1, "host": "h", "event": "checked", "bytes": 10, "note": CANARY} for _ in range(120)])
    hist = write(os.path.join(d, "hist_canary.jsonl"), [rec(100, {"Bash": 50.0, "Read": 50.0})])
    rc, out = run(["--history", hist, "--ledger", led, "--scan", os.path.join(d, "profile"), "--min-turns", "1"])
    check("laporan manusia: kenari TIDAK muncul", CANARY in out, False)
    check("laporan manusia: path transcript TIDAK muncul", tp in out, False)
    rc, js = run(["--history", hist, "--ledger", led, "--scan", os.path.join(d, "profile"),
                  "--min-turns", "1", "--json"])
    check("JSON: kenari TIDAK muncul", CANARY in js, False)
    check("JSON: path TIDAK muncul", (tp in js) or (d in js), False)
    payload = json.loads(js)
    check("JSON: hanya agregat (nol isi alat)", "carry_shares" in (payload.get("live") or {}), True)
    check("JSON: hasil dinyatakan", payload["status"] in ("CANDIDATE", "NO_ACTION"), True)
    check("JSON: mutasi kebijakan NONE", payload["policy_mutation"], False)

    cand = os.path.join(d, "candidates")
    rc, out = run(["--history", hist, "--ledger", led, "--scan", os.path.join(d, "profile"),
                   "--min-turns", "1", "--emit-candidate", cand])
    files = [os.path.join(r, f) for r, _, fs in os.walk(cand) for f in fs]
    check("spesifikasi kandidat ditulis", bool(files), True)
    blob = "".join(open(f, encoding="utf-8").read() for f in files)
    check("spesifikasi kandidat: kenari TIDAK muncul", CANARY in blob, False)
    check("spesifikasi kandidat: path TIDAK muncul", (d in blob) or (tp in blob), False)
    check("spesifikasi kandidat menyebut gerbang promosi", "HELD_OUT_CONFIRMATION" in blob, True)
    check("spesifikasi kandidat menyebut anggaran instruksi", "always-on bytes delta" in blob, True)

    # ---------------------------------------------------------------- nol mutasi kebijakan
    watched = []
    for base in ("skills", "hooks", ".claude-plugin"):
        for r, _, fs in os.walk(os.path.join(ROOT, base)):
            for f in fs:
                if f.endswith((".md", ".py", ".sh", ".json")):
                    watched.append(os.path.join(r, f))
    before = {q: hashlib.sha256(open(q, "rb").read()).hexdigest() for q in watched}
    run(["--history", hist, "--ledger", led, "--scan", os.path.join(d, "profile"), "--min-turns", "1",
         "--emit-candidate", cand])
    after = {q: hashlib.sha256(open(q, "rb").read()).hexdigest() for q in watched}
    check("skills/, hooks/, .claude-plugin/ byte-identik sesudah dijalankan", after, before)

    src = open(OPT, encoding="utf-8").read()
    for bad in ("import socket", "import urllib", "import http", "import requests", "urlopen(",
                "anthropic", "subprocess", "os.system", "curl "):
        check(f"nol jalur luar: '{bad}' tak ada di sumber", bad in src, False)
    check("nol pemanggilan model: 'claude' tak muncul sebagai perintah",
          any(x in src for x in ("claude -p", '"claude"', "'claude'")), False)

    # ---------------------------------------------------------------- overhead observer
    t0 = time.time()
    run(["--history", hist, "--ledger", led, "--scan", os.path.join(d, "profile"), "--min-turns", "1"])
    dt = time.time() - t0
    check(f"satu run selesai dalam waktu terbatas (terukur {dt:.1f} s, plafon 120 s)", dt < 120, True)
    check("berkas history tetap satu baris per run (nol telemetri kedua)",
          sum(1 for _ in open(hist)), 1)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
