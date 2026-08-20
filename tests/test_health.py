#!/usr/bin/env python3
"""Suite mandiri utk tools/health.py — pola ~/scripts: nol runner agregat."""
import json, os, subprocess, sys, tempfile, time

HEALTH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "health.py")
PASS = FAIL = 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1; print(f"  PASS  {name}")
    else:
        FAIL += 1; print(f"  FAIL  {name}: dapat {got!r}, harap {want!r}")


def run(args):
    return subprocess.run(["/usr/bin/python3", HEALTH] + args,
                          capture_output=True, text=True, timeout=30).stdout


def ledger(path, age_h, n=3):
    ts = int(time.time() - age_h * 3600)
    with open(path, "w") as fh:
        for _ in range(n):
            fh.write(json.dumps({"ts": ts, "host": "t", "event": "checked", "same": False}) + "\n")
        fh.write(json.dumps({"ts": ts, "host": "t", "event": "denied", "bytes": 10}) + "\n")


def sess(d, age_h):
    p = os.path.join(d, "s.jsonl")
    open(p, "w").write("{}\n")
    t = time.time() - age_h * 3600
    os.utime(p, (t, t))


with tempfile.TemporaryDirectory() as d:
    led = os.path.join(d, "l.jsonl"); sd = os.path.join(d, "sess"); os.mkdir(sd)
    rl = os.path.join(d, "run.jsonl")

    # 1. sesi segar + ledger segar -> sehat, nol alert
    ledger(led, 1); sess(sd, 1)
    out = run(["--ledgers", led, "--sessions", sd, "--runlog", rl])
    check("sehat -> nol alert", "ALERT|" in out, False)
    check("ringkasan memuat hitungan", "checked=3 denied=1" in out, True)
    rec = json.loads(open(rl).read().strip().split("\n")[-1])
    check("rekaman run tertulis", (rec["checked"], rec["denied"]), (3, 1))

    # 2. sesi segar tapi ledger membeku 40 jam -> guard patut dicurigai lepas
    ledger(led, 40); sess(sd, 1)
    check("ledger beku + sesi aktif -> ALERT stale",
          "ALERT|MED|stale|" in run(["--ledgers", led, "--sessions", sd]), True)

    # 3. sesi ikut sepi -> DIAM (ledger diam itu wajar, bukan kerusakan)
    ledger(led, 40); sess(sd, 40)
    check("sesi sepi -> tak ada alert",
          "ALERT|" in run(["--ledgers", led, "--sessions", sd]), False)

    # 4. ledger kosong tapi baru dibuat -> masa tenggang, jangan berisik
    open(led, "w").close(); sess(sd, 1)
    check("ledger baru kosong -> tenggang",
          "ALERT|" in run(["--ledgers", led, "--sessions", sd]), False)

    # 5. ledger kosong sejak lama + sesi aktif -> guard tak pernah menembak
    t = time.time() - 100 * 3600
    os.utime(led, (t, t))
    check("kosong >72j + sesi aktif -> ALERT",
          "ALERT|MED|stale|" in run(["--ledgers", led, "--sessions", sd]), True)

    # 6. field tambahan ikut terekam (status i9, rc feed)
    ledger(led, 1)
    run(["--ledgers", led, "--sessions", sd, "--runlog", rl,
         "--field", "i9=absent", "--field", "feed_rc=0"])
    rec = json.loads(open(rl).read().strip().split("\n")[-1])
    check("field tambahan terekam", (rec.get("i9"), rec.get("feed_rc")), ("absent", "0"))

    # 7. runlog tak bisa ditulis -> lapor, jangan diam
    check("runlog mustahil -> ALERT failed",
          "ALERT|MED|failed|" in run(["--ledgers", led, "--sessions", sd,
                                      "--runlog", "/proc/x/y.jsonl"]), True)

print(f"\n{PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
