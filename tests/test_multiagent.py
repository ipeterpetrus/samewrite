#!/usr/bin/env python3
"""AI-VOS suite: SameWrite's measurement layer under a population of agents that never stops.

Not "does it work on my laptop" but: many agents, several roles, parallel writers, crashes,
clock skew, bounded sweeps, a scheduler calling it every cycle. Every check below is a property
that breaks silently — a merged population, a candidate invented from half a corpus, a proposal
rewritten every hour — rather than one that raises.

Standalone: run this file. No runner, no fixtures, no conftest."""
import collections, json, multiprocessing as mp, os, socket, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import carry, optimize  # noqa: E402
import evidence_history  # noqa: E402  (the history file, read through the frozen kernel)
from evidence.absence import Absence  # noqa: E402
from evidence.container import history_integrity  # noqa: E402
from evidence.values import make_epoch, make_scope_id  # noqa: E402

OPT = os.path.join(ROOT, "tools", "optimize.py")
P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


def rec(ts, shares, scope="default", turns=1000, sessions=40, **kw):
    r = {"schema_version": 2, "record_type": "carry_run", "ts": ts, "sessions": sessions,
         "turns": turns, "carry_bytes": 10 ** 7, "scanned": 100, "scope_id": scope,
         "workload_class": "", "evidence_quality": "COMPLETE",
         "run_id": kw.pop("run_id", None) or carry.new_run_id(),
         "shares": shares, "bpt": {k: 1.0 for k in shares}}
    r.update(kw)
    return r


def write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    return path


def run(args):
    p = subprocess.run([sys.executable, OPT] + args, capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def acc(sessions, turns=1000, quality="COMPLETE", carry_map=None):
    return {"sessions": sessions, "turns": turns, "scanned": sessions, "short": 0,
            "unreadable": 0, "oversize": 0, "skipped_by_limit": 0, "quality": quality,
            "carry": collections.Counter(carry_map or {"Bash": 90, "Read": 10})}


EMPTY_HIST = {"comparable": [], "total": 0, "in_scope": 0, "rejected": {}, "dropped": [],
              "time_order": "ok"}


# ---------------------------------------------------------------- workers (module level: fork pools)
def _facts(i, sources=2):
    """Acquisition facts the way accumulate() now returns them.

    OLD_SEMANTIC: the writer handed carry.history() a dict of totals; the record was assembled
    from it by hand.
    NEW_FROZEN_SEMANTIC: a record is built through the frozen constructors, so the facts must
    include what the certificate is made of — one outcome per SELECTED source, the identity each
    source had, and the digest of the bytes read from each source that parsed.
    WHY: a producer that can skip a field the reader validates is the divergence this whole
    generation exists to remove. The fixture carries the same obligation as production.
    """
    parsed = {("/x/%d/%d.jsonl" % (i, k)): {"content": "%064x" % (i * 100 + k), "turns": 10}
              for k in range(sources)}
    identities = {path: {"dev": 1, "inode": 1000 + k, "size": 10, "mtime_ns": 1}
                  for k, path in enumerate(sorted(parsed))}
    return {"sessions": 40, "turns": 1000 + i, "lengths": [10] * 40, "quality": "COMPLETE",
            "carry": collections.Counter({"Bash": 60, "Read": 40}), "size": {"Bash": 1, "Read": 1},
            "usage": collections.Counter(), "runtimes": {"2.1.270": 1}, "models": {"m1": 1},
            "unreadable": 0, "oversize": 0, "skipped_by_limit": 0, "scanned": sources, "short": 0,
            "sources": identities, "parsed": parsed, "sample_bound": 0,
            "counters": {"discovered": sources, "skipped_by_limit": 0, "unreadable": 0,
                         "oversize": 0, "identity_changed": 0, "empty_source": 0,
                         "not_attempted": 0, "malformed": 0, "records_rejected": 0,
                         "dirs_unreadable": 0}}


def _writer(args):
    path, scope, i = args
    carry.history(path, _facts(i), 100, scope_id=scope)  # C = jumlah carry, share berjumlah 100
    return True


def _emitter(args):
    outdir, hist, empty = args
    p = subprocess.run([sys.executable, OPT, "--history", hist, "--ledger", empty, "--scan",
                        "--emit-candidate", outdir], capture_output=True, text=True, timeout=600)
    return p.stdout + p.stderr


def main():
    d = tempfile.mkdtemp(prefix="sw-aivos-")
    empty = os.path.join(d, "none.jsonl")

    # ------------------------------------------------------------ 1. scope isolation
    mixed = [rec(100 + i * 86400, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8}, scope="builder")
             for i in range(6)]
    mixed += [rec(100 + i * 86400, {"Bash": 80.0, "Read": 20.0}, scope="reviewer") for i in range(6)]
    p = write(os.path.join(d, "mixed.jsonl"), mixed)
    recs, _, _ = optimize.load_history(p)
    check("dua scope terbaca utuh", len(recs), 12)
    groups = optimize.by_scope(recs)
    check("record dikelompokkan per scope", sorted(groups), ["builder", "reviewer"])
    keep, dropped = optimize.comparable(recs)
    check("comparable() menolak mencampur scope", {optimize.scope_of(r) for r in keep},
          {optimize.scope_of(max(recs, key=lambda r: r.get("ts") or 0))})
    check("penolakan lintas-scope dilaporkan, bukan senyap",
          any("scope" in why for _, why in dropped), True)

    rc, out = run(["--history", p, "--ledger", empty, "--scan", "--scope-id", "reviewer"])
    check("scope reviewer: nol tren (share datar)", "trend-bash" in out, False)
    check("scope lain disebut, tak dilebur", "builder" in out, True)
    rc, out = run(["--history", p, "--ledger", empty, "--scan", "--scope-id", "builder"])
    check("scope builder: tren dilaporkan di scope-nya sendiri", "trend-bash" in out, True)

    wl = [rec(100 + i * 86400, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8}, scope="ops",
              workload_class="audit" if i < 3 else "build") for i in range(6)]
    keep_wl, dropped_wl = optimize.comparable(wl)
    check("kelas beban berubah -> WORKLOAD_SHIFT, bukan tren", len(keep_wl), 3)
    check("alasan workload dinamai", any("WORKLOAD_SHIFT" in why for _, why in dropped_wl), True)

    # ------------------------------------------------------------ 2. role isolation matrix
    roles = ["BUILDER", "REVIEWER", "OPS", "RESEARCH"]
    rolerecs = []
    for n, role in enumerate(roles):
        rolerecs += [rec(100 + i * 86400, {"Bash": 20.0 + n * 20, "Read": 80.0 - n * 20},
                         scope=role) for i in range(5)]
    p = write(os.path.join(d, "roles.jsonl"), rolerecs)
    ids = {}
    for role in roles:
        rc, js = run(["--history", p, "--ledger", empty, "--scan", "--scope-id", role, "--json"])
        o = json.loads(js)
        check(f"{role}: hanya record scope-nya dipakai", o["scope"]["records_in_scope"], 5)
        check(f"{role}: scope yang dianalisis benar", o["scope"]["analysed"], role)
        check(f"{role}: tiga scope lain terlihat tapi tak dilebur", len(o["scope"]["known"]), 4)
        ids[role] = set(o["candidate_ids"])
    check("nol candidate_id dipakai-bersama antar peran",
          all(not (ids[a] & ids[b]) for a in roles for b in roles if a != b), True)

    live = acc(40)
    fa = optimize.analyse(live, EMPTY_HIST, None, None, scope="BUILDER")
    fb = optimize.analyse(live, EMPTY_HIST, None, None, scope="REVIEWER")
    check("bukti identik, scope beda -> candidate_id beda",
          fa[0]["candidate_id"] != fb[0]["candidate_id"], True)
    check("temuan dari satu scope tak mengklaim semua orang", fa[0]["scope_claim"], "SCOPE_LOCAL")

    # ------------------------------------------------------------ 3. identitas run
    ids32 = {carry.new_run_id() for _ in range(5000)}
    check("5000 run_id unik", len(ids32), 5000)
    # OLD_SEMANTIC: 32 hex characters (uuid4().hex).
    # NEW_FROZEN_SEMANTIC: a lowercase version-4 UUID, 36 characters with dashes — the exact form
    # `evidence.values.make_run_id` accepts.
    # WHY: the identity a record is WRITTEN with must be the identity the reader VALIDATES. Two
    # spellings of the same id is how a producer and a decoder start disagreeing about what is
    # even a record.
    check("run_id berbentuk UUID4 huruf kecil",
          all(len(x) == 36 and x.count("-") == 4 and x[14] == "4" for x in ids32), True)

    # ------------------------------------------------------------ 4. penulis paralel 32 & 64
    for n in (32, 64):
        hp = os.path.join(d, f"conc{n}.jsonl")
        open(hp, "w").close()
        with mp.get_context("fork").Pool(min(n, 16)) as pool:
            pool.map(_writer, [(hp, "conc", i) for i in range(n)])
        lines = [l for l in open(hp, encoding="utf-8").read().splitlines() if l.strip()]
        check(f"{n} penulis paralel: {n} baris, nol yang robek", len(lines), n)
        parsed = []
        for l in lines:
            try:
                parsed.append(json.loads(l))
            except Exception:
                parsed.append(None)
        check(f"{n} penulis paralel: setiap baris JSON utuh", parsed.count(None), 0)
        # OLD_SEMANTIC: run_id sat at the top level of a flat record.
        # NEW_FROZEN_SEMANTIC: it is in the envelope, with the record's position beside it.
        # WHY: the envelope is the record's own header; a reader that has to guess which level a
        # field lives at is a reader with two schemas.
        check(f"{n} penulis paralel: run_id semua berbeda",
              len({o["envelope"]["run_id"] for o in parsed}), n)
        # The chain the contract requires: n records, positions 0..n-1, each linked to the one
        # before it. This is what the lock in evidence_history buys — without it every writer
        # would claim the same position and the container would be permanently degraded.
        check(f"{n} penulis paralel: posisi 0..{n - 1} tanpa tabrakan",
              sorted(o["envelope"]["run_seq"] for o in parsed), list(range(n)))
        container = evidence_history.read_container(hp)
        state = history_integrity(container, Absence.KNOWN_ABSENT,
                                  make_scope_id("conc"), make_epoch(int(time.time())))
        check(f"{n} penulis paralel: container INTACT", state.integrity.value, "INTACT")
        # OLD_SEMANTIC: the 1.3 optimizer read every record this writer produced.
        # NEW_FROZEN_SEMANTIC: it reads NONE of them, by refusing the schema it was never
        # written against.
        # WHY: phase 2 ports acquisition, not promotion. An optimizer that guessed at a
        # current-generation record would be reading fields whose meaning it does not know —
        # the exact "legacy gains current trust" failure, in the other direction.
        recs, rej, _ = optimize.load_history(hp)
        check(f"{n} penulis paralel: optimizer 1.3 menolak skema baru, fail closed",
              (len(recs), sum(rej.values())), (0, n))

    # ------------------------------------------------------------ 5. konsistensi pasca-crash
    # Blank lines are filtered out of the SETUP, not out of an assertion. Under 64 concurrent
    # writers the append guard in carry.history() occasionally emits one: the kernel extends a file
    # page by page, so an in-flight append is briefly visible as a tail with no newline, the guard
    # cannot tell that from a crash-truncated tail, and it inserts a separator that turns out not to
    # have been needed. Measured on this machine: ~10 rounds in 40 at 64 writers, and with the guard
    # removed entirely, 0 in 40 — so the guard is the source and the effect is cosmetic. Every
    # record still lands intact (64 lines, 64 parsed, 64 distinct run_ids in every round) and both
    # readers skip blank lines. What this section tests is that a TORN line is rejected and the good
    # records around it survive; an unrelated blank line in the fixture would shift the slice below
    # and fail that test for a reason it is not about.
    good = [l for l in open(os.path.join(d, "conc32.jsonl"), encoding="utf-8").read().splitlines()
            if l.strip()]
    torn = os.path.join(d, "torn.jsonl")
    with open(torn, "w", encoding="utf-8") as fh:
        fh.write("\n".join(good[:10]) + "\n")
        fh.write(good[10][:len(good[10]) // 2])            # mati di tengah baris
    # OLD_SEMANTIC: the torn file was read by the 1.3 optimizer, which counted the good records.
    # NEW_FROZEN_SEMANTIC: the records are current-generation, so the reader that can see them is
    # the frozen container reader; the torn line is a REJECTION and the container says so.
    # WHY: container damage must remain observable, and the 1.3 optimizer no longer reads this
    # generation at all (see section 4).
    before = evidence_history.read_container(torn)
    check("baris terpotong ditolak, sisanya selamat", len(before.records), 10)
    check("baris terpotong dihitung sebagai tolakan", before.lines_rejected, 1)
    torn_state = history_integrity(before, Absence.KNOWN_ABSENT, make_scope_id("conc"),
                                   make_epoch(int(time.time())))
    check("container dengan baris robek TIDAK pernah INTACT",
          torn_state.integrity.value in ("DEGRADED", "UNVERIFIED"), True)
    carry.history(torn, _facts(99), 100, scope_id="conc")   # penulis berikutnya sesudah crash
    after = evidence_history.read_container(torn)
    check("penulisan sesudah crash tetap terbaca", len(after.records), 11)
    check("record baru tak dilem ke baris yang robek", after.lines_rejected, 1)

    # ------------------------------------------------------------ 6. reentrancy: dua penjadwal
    hist = write(os.path.join(d, "hist.jsonl"), [rec(100, {"Bash": 50.0, "Read": 50.0})])
    rise = write(os.path.join(d, "rise.jsonl"),
                 [rec(100 + i * 86400 * 7, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8},
                      scope="sched") for i in range(6)])
    out1 = os.path.join(d, "cand_reentrant")
    os.makedirs(out1)
    with optimize.Lock(os.path.join(out1, ".optimize.lock")) as got:
        check("kunci pertama diberikan", got, True)
        with optimize.Lock(os.path.join(out1, ".optimize.lock")) as second:
            check("kunci kedua DITOLAK, bukan menunggu selamanya", second, False)
    with optimize.Lock(os.path.join(out1, ".optimize.lock")) as third:
        check("kunci dilepas sesudah keluar blok", third, True)

    with mp.get_context("fork").Pool(4) as pool:
        outs = pool.map(_emitter, [(out1, rise, empty)] * 4)
    files = [os.path.join(r, f) for r, _, fs in os.walk(out1) for f in fs if f.endswith(".md")]
    check("4 penjadwal serentak: nol berkas .tmp tertinggal",
          [f for r, _, fs in os.walk(out1) for f in fs if ".tmp-" in f], [])
    blobs = {open(f, encoding="utf-8").read() for f in files}
    check("4 penjadwal serentak: setiap spesifikasi utuh & unik", len(blobs), len(files))
    check("penjadwal yang kalah lomba melapor, bukan menimpa",
          any(("ALREADY_RUNNING" in o) or ("EXISTING_CANDIDATE" in o) for o in outs), True)

    # ------------------------------------------------------------ 7. sapuan parsial = fail-closed
    part = acc(40, quality="PARTIAL")
    f_part = optimize.analyse(part, EMPTY_HIST, None, None, scope="s")
    check("bukti PARTIAL -> nol kandidat", [x["state"] for x in f_part], ["OBSERVED"])
    check("alasan PARTIAL dicetak di bukti", "PARTIAL" in f_part[0]["evidence"], True)
    f_ok = optimize.analyse(part, EMPTY_HIST, None, None, scope="s", accept_partial=True)
    check("PARTIAL + --accept-partial (korpus terbatas disengaja) -> kandidat",
          f_ok[0]["state"], "CANDIDATE")
    check("status keseluruhan untuk PARTIAL tanpa izin",
          optimize.overall_status(f_part, EMPTY_HIST, part, optimize.population([]), False),
          "PARTIAL_EVIDENCE")
    inval = acc(0, quality="INVALID")
    check("bukti INVALID -> nol temuan sama sekali",
          optimize.analyse(inval, EMPTY_HIST, None, None), [])

    # ------------------------------------------------------------ 8. id kandidat deterministik
    f1 = optimize.analyse(acc(40), EMPTY_HIST, None, None, scope="x")[0]
    f2 = optimize.analyse(acc(41), EMPTY_HIST, None, None, scope="x")[0]
    check("bukti yang sama -> candidate_id sama (nol spam usulan)",
          f1["candidate_id"], f2["candidate_id"])
    far = optimize.analyse(acc(40, carry_map={"Bash": 40, "Read": 60}), EMPTY_HIST, None, None,
                           scope="x")[0]
    check("bukti bergerak melewati ambang material -> candidate_id BARU",
          far["candidate_id"] != f1["candidate_id"], True)
    check("candidate_id membawa scope-nya", f1["candidate_id"].split("-")[-2], "x")

    out2 = os.path.join(d, "cand_dedup")
    w, e, _fail = optimize.emit_candidates([f1], out2)
    check("emisi pertama menulis", (len(w), len(e)), (1, 0))
    w, e, _fail = optimize.emit_candidates([f2], out2)
    check("emisi kedua dgn bukti setara: EXISTING, nol penulisan ulang", (len(w), len(e)), (0, 1))
    w, e, _fail = optimize.emit_candidates([far], out2)
    check("bukti yang benar-benar bergerak: kandidat baru ditulis", (len(w), len(e)), (1, 0))

    # ------------------------------------------------------------ 8b. identitas tren stabil
    def hist_of(n, step=8.0):
        rows = [rec(100 + i * 86400 * 7, {"Bash": 30.0 + i * step, "Read": 70.0 - i * step},
                    scope="t") for i in range(n)]
        return {"comparable": rows, "total": n, "in_scope": n, "rejected": {}, "dropped": [],
                "time_order": "ok"}

    ids = []
    for n in (4, 6, 8, 10, 12):
        f = [x for x in optimize.analyse(None, hist_of(n), None, None, scope="t")
             if x["id"] == "trend-bash"]
        ids.append(f[0]["candidate_id"] if f else None)
    # Kemiringan yang dicocokkan pada jendela yang MEMBESAR meluruh walau dunianya berhenti
    # bergerak. Identitas yang mengikuti besarannya akan mencetak usulan baru tiap kali penaksir
    # mengendap — churn yang lahir dari alat ukur, bukan dari dunia.
    check("gerakan yang sama, jendela membesar -> SATU identitas kandidat", len(set(ids)), 1)
    down = [rec(100 + i * 86400 * 7, {"Bash": 80.0 - i * 8.0, "Read": 20.0 + i * 8.0}, scope="t")
            for i in range(6)]
    hd = {"comparable": down, "total": 6, "in_scope": 6, "rejected": {}, "dropped": [],
          "time_order": "ok"}
    fdown = [x for x in optimize.analyse(None, hd, None, None, scope="t")
             if x["id"] == "trend-bash"][0]
    check("PEMBALIKAN arah -> identitas BARU (saat manusia memang harus melihat lagi)",
          fdown["candidate_id"] != ids[0], True)

    # Vektor share berjumlah 100: satu sumber naik BERARTI sumber lain turun. Melaporkan keduanya
    # adalah gerakan yang sama dua kali.
    ftr = [x for x in optimize.analyse(None, hist_of(6), None, None, scope="t")
           if x["id"].startswith("trend-")]
    check("cermin tak dilaporkan sebagai kandidat kedua", len(ftr), 1)
    check("gerakan komplemen tetap DISEBUT di bukti, bukan dibuang diam-diam",
          "other direction" in ftr[0]["evidence"], True)

    # ------------------------------------------------------------ 9. ikatan bukti
    spec = open(os.path.join(out2, f1["candidate_id"], "HYPOTHESIS.md"), encoding="utf-8").read()
    for token in ("candidate_id:", "scope_id:", "threshold_schema_version:", "optimizer_version:",
                  "evidence_bucket:", "evidence_run_ids:", "samewrite_version:"):
        check(f"spesifikasi mengikat bukti: {token}", token in spec, True)
    check("spesifikasi membawa invarian bukti (anti-truncate)",
          "Never truncate the only copy of evidence" in spec, True)
    # Aturan pelestarian bukti TANPA pengecualian rahasia akan mengawetkan token yang bocor dan
    # menyebutnya arsip. Kanonik AI-VOS memisahkan keduanya; spesifikasi harus ikut.
    check("invarian bukti membawa pengecualian rahasia (bukan mengawetkan kebocoran)",
          "secret material is never the evidence" in spec, True)
    check("pengecualian rahasia menyebut apa yang TETAP disimpan",
          "never the value" in spec, True)
    check("spesifikasi membawa invarian scope (anti-uninstall)",
          "never an instruction to uninstall anything globally" in spec, True)

    # ------------------------------------------------------------ 10. kontrak keluaran & versi
    rc, js = run(["--history", rise, "--ledger", empty, "--scan", "--json"])
    o = json.loads(js)
    for k in ("output_schema_version", "optimizer_version", "threshold_schema_version",
              "samewrite_version", "status", "status_code", "scope", "history", "findings",
              "candidate_ids", "policy_mutation", "evidence_quality"):
        check(f"skema JSON: kunci '{k}' ada", k in o, True)
    check("skema JSON berversi", o["output_schema_version"], optimize.OUTPUT_SCHEMA_VERSION)
    check("ambang berversi terpisah dari alat", o["threshold_schema_version"],
          optimize.THRESHOLD_SCHEMA_VERSION)
    check("status_code cocok dgn status", o["status_code"], optimize.STATUS[o["status"]])
    check("setiap kandidat membawa versi ambang yang memproduksinya",
          all(x["threshold_schema_version"] == optimize.THRESHOLD_SCHEMA_VERSION
              for x in o["findings"]), True)

    rc, _ = run(["--history", rise, "--ledger", empty, "--scan"])
    check("jalan sah -> exit 0 (penjadwal tak salah baca 'nihil' sbg rusak)", rc, 0)
    rc, _ = run(["--history", rise, "--ledger", empty, "--scan", "--strict-exit"])
    check("--strict-exit memetakan status ke exit code", rc, optimize.STATUS["CANDIDATE"])
    rc, _ = run(["--history", empty, "--ledger", empty, "--scan", "--strict-exit"])
    check("nol bukti + --strict-exit -> INSUFFICIENT_DATA", rc, optimize.STATUS["INSUFFICIENT_DATA"])

    # ------------------------------------------------------------ 11. penolakan jaringan DINAMIS
    # Grep sumber membuktikan tak ada import; ini membuktikan tak ada PANGGILAN, termasuk lewat
    # pustaka pihak ketiga yang diimpor belakangan.
    calls = []
    real = (socket.socket, socket.create_connection, socket.getaddrinfo)

    def deny(*a, **k):
        calls.append(a)
        raise AssertionError("optimizer mencoba membuka jaringan")

    socket.socket = deny
    socket.create_connection = deny
    socket.getaddrinfo = deny
    try:
        optimize.main(["--history", rise, "--ledger", empty, "--scan", "--json"])
        net_ok = True
    except AssertionError:
        net_ok = False
    finally:
        socket.socket, socket.create_connection, socket.getaddrinfo = real
    check("jalan penuh dgn jaringan DIMATIKAN: selesai normal", net_ok, True)
    check("nol percobaan soket tercatat", calls, [])

    # ------------------------------------------------------------ 12. baris patologis / tak dipercaya
    prof = os.path.join(d, "profile", "projects", "-repo")
    os.makedirs(prof)
    tp = os.path.join(prof, "s.jsonl")
    rows = []
    for i in range(60):
        rows.append({"type": "assistant", "version": "2.1.270",
                     "message": {"model": "m", "usage": {"input_tokens": 1, "output_tokens": 1},
                                 "content": [{"type": "tool_use", "id": str(i), "name": "Bash",
                                              "input": {"command": "x"}}]}})
        rows.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": str(i), "content": "ok"}]}})
    write(tp, rows)
    with open(tp, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "big",
             "content": "A" * (carry.MAX_LINE + 10)}]}}) + "\n")
        fh.write("\x00\x01\x02 bukan json, byte mentah\n")
        fh.write(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "z", "name": "\x1b[31mBash\x1b[0m", "input": {}}]}}) + "\n")
    t0 = time.time()
    a = carry.accumulate([tp], min_turns=1)
    dt = time.time() - t0
    check("baris 8 MB dilewati DAN dihitung", a["oversize"], 1)
    check("baris raksasa membuat bukti PARTIAL, bukan diam-diam lengkap", a["quality"], "PARTIAL")
    # Plafon LONGGAR dengan sengaja. Yang dijaga invarian ini adalah ledakan kompleksitas (O(n^2)
    # pada baris 8 MB = MENIT), bukan beberapa detik. Ambang ketat pada mesin yang sedang sibuk
    # menghasilkan uji yang gagal acak — dan uji yang gagal acak akan diabaikan, lalu berhenti
    # menjaga apa pun. Angka ANGGARAN yang sesungguhnya diukur di experiments/scale/scan_scale.py.
    check(f"baris patologis tak meledakkan waktu (terukur {dt:.1f} s, plafon 120 s)", dt < 120, True)
    rc, out = run(["--history", empty, "--ledger", empty, "--scan", os.path.join(d, "profile"),
                   "--min-turns", "1"])
    check("laporan menyebut baris yang dilewati", "oversized" in out, True)
    check("byte kendali dari transcript tak dipercaya tak lolos ke terminal",
          "\x1b[31m" in out, False)
    check("label dibersihkan di SATU tempat, bukan per pemanggil",
          carry.bucket("attach:\x1b[31mhook\x07"), "attach:[31mhook")

    # ------------------------------------------------------------ 13. mode terbatas (max-files)
    more = os.path.join(d, "profile", "projects", "-repo2")
    os.makedirs(more)
    for k in range(4):
        write(os.path.join(more, f"s{k}.jsonl"), rows)
    allp = [tp] + [os.path.join(more, f"s{k}.jsonl") for k in range(4)]
    a_all = carry.accumulate(allp, min_turns=1)
    a_cap = carry.accumulate(allp, min_turns=1, max_files=2)
    check("max-files membatasi sapuan", (a_cap["scanned"], a_all["scanned"]), (2, 5))
    check("sapuan terbatas ditandai PARTIAL", a_cap["quality"], "PARTIAL")
    check("berapa yang dilewati dicatat", a_cap["skipped_by_limit"], 3)
    # Sebuah batas harus berarti "N TERBARU". Prefiks alfabetis dari arsip panjang-umur adalah
    # sampel dari yang dibuat paling awal — irisan paling tak informatif untuk populasi 24x7.
    old_one = os.path.join(more, "s0.jsonl")
    new_one = os.path.join(more, "s3.jsonl")
    os.utime(old_one, (1, 1))
    os.utime(new_one, (2 * 10 ** 9, 2 * 10 ** 9))
    picked = []
    real_scan = carry.scan_full
    carry.scan_full = lambda q: (picked.append(q), real_scan(q))[1]
    try:
        carry.accumulate([old_one] + [os.path.join(more, f"s{k}.jsonl") for k in (1, 2, 3)],
                         min_turns=1, max_files=1)
    finally:
        carry.scan_full = real_scan
    check("mode terbatas mengambil transcript TERBARU, bukan yang pertama menurut abjad",
          picked, [new_one])

    # ------------------------------------------------------------ 14. independen dari jam
    same_ts = [rec(500, {"Bash": 30.0 + i * 10, "Read": 70.0 - i * 10}, scope="skew")
               for i in range(5)]
    p = write(os.path.join(d, "skew.jsonl"), same_ts)
    rc, out = run(["--history", p, "--ledger", empty, "--scan", "--scope-id", "skew"])
    check("stempel waktu identik -> TREND_AMBIGUOUS, nol arah diklaim",
          "TREND_AMBIGUOUS" in out, True)
    check("stempel ambigu -> nol kandidat tren", "trend-bash" in out, False)
    back = [rec(1000 - i * 86400, {"Bash": 30.0 + i * 10, "Read": 70.0 - i * 10}, scope="skew2")
            for i in range(5)]
    p = write(os.path.join(d, "back.jsonl"), back)
    rc, out = run(["--history", p, "--ledger", empty, "--scan", "--scope-id", "skew2"])
    check("jam mundur -> nol tren dilaporkan", "trend-bash" in out, False)

    # ------------------------------------------------------------ 15. record gabung-lintas-host
    h1 = [rec(100 + i * 86400, {"Bash": 40.0, "Read": 60.0}, scope="fleet") for i in range(3)]
    h2 = [rec(100 + i * 86400, {"Bash": 41.0, "Read": 59.0}, scope="fleet") for i in range(3)]
    merged = write(os.path.join(d, "fleet.jsonl"), h1 + h2)   # dua host, satu scope, digabung
    recs, rej, _ = optimize.load_history(merged)
    check("record dua host dalam satu scope bisa digabung tanpa tabrakan", len(recs), 6)
    check("nol tolakan saat penggabungan", sum(rej.values()), 0)
    dup = write(os.path.join(d, "fleet_dup.jsonl"), h1 + h2 + h1)  # rsync menyalin dua kali
    recs, rej, _ = optimize.load_history(dup)
    check("penggabungan ulang idempoten (run_id sama = satu observasi)", len(recs), 6)
    check("salinan ganda dihitung sebagai retry", rej["duplicate run_id (retry)"], 3)

    # ------------------------------------------------------------ 16. nol biaya konteks model
    refs = []
    for base in ("skills", "hooks", ".claude-plugin"):
        for r, _, fs in os.walk(os.path.join(ROOT, base)):
            for f in fs:
                q = os.path.join(r, f)
                try:
                    if "optimize.py" in open(q, encoding="utf-8", errors="replace").read():
                        refs.append(os.path.relpath(q, ROOT))
                except OSError:
                    pass
    check("optimize.py tak dirujuk skill/hook/manifest mana pun", refs, [])
    check("record history tetap satu baris per run", sum(1 for _ in open(hist)), 1)

    # ------------------------------------------------------------ 17. anggaran sumber daya
    big = os.path.join(d, "budget.jsonl")
    write(big, [rec(100 + i * 3600, {"Bash": 50.0, "Read": 50.0}, scope="b") for i in range(20000)])
    t0 = time.time()
    recs, _, _ = optimize.load_history(big)
    dt = time.time() - t0
    check("20k record terbaca", len(recs), 20000)
    check(f"20k record dalam waktu terbatas (terukur {dt:.1f} s, plafon 120 s)", dt < 120, True)
    check("history 20k run masih < 50 MB di disk", os.path.getsize(big) < 50 * 10 ** 6, True)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
