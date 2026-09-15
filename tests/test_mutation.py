#!/usr/bin/env python3
"""Mutation tests: prove the AI-VOS invariants are actually TESTED, not merely asserted.

A suite that is green on a broken implementation is decoration. For each invariant below the
implementation is deliberately broken in a temporary copy of `tools/`, and the oracle for that
invariant must go RED; the same oracle must then be GREEN against the real source. An invariant
whose mutant stays green is reported as UNGUARDED — the test suite, not the tool, is the defect.

Nothing here touches the repository: every mutation happens in a throwaway copy.

Standalone: run this file."""
import os, shutil, subprocess, sys, tempfile, textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
P = F = 0


def report(label, red_on_mutant, green_on_real, detail=""):
    global P, F
    if red_on_mutant and green_on_real:
        P += 1
        print(f"  PASS  {label}: mutan MERAH, asli HIJAU")
    else:
        F += 1
        why = ("mutan tetap HIJAU — invarian TAK DIJAGA" if not red_on_mutant
               else "asli MERAH — oracle atau implementasi salah")
        print(f"  FAIL  {label}: {why}. {detail}")


def oracle(toolsdir, body):
    """Run an invariant check against one copy of tools/. -> (holds, output)."""
    src = textwrap.dedent(f"""
        import sys, collections, json, os, tempfile
        sys.path.insert(0, {toolsdir!r})
        import carry, optimize
        EMPTY_HIST = {{"comparable": [], "total": 0, "in_scope": 0, "rejected": {{}},
                      "dropped": [], "time_order": "ok"}}
        def acc(sessions=40, turns=1000, quality="COMPLETE", carry_map=None):
            return {{"sessions": sessions, "turns": turns, "scanned": sessions, "short": 0,
                    "unreadable": 0, "oversize": 0, "skipped_by_limit": 0, "quality": quality,
                    "carry": collections.Counter(carry_map or {{"Bash": 90, "Read": 10}})}}
        def rec(ts, shares, scope="default", turns=1000, run_id=None):
            return {{"schema_version": 2, "record_type": "carry_run", "ts": ts, "sessions": 40,
                    "turns": turns, "carry_bytes": 10**7, "scope_id": scope, "workload_class": "",
                    "evidence_quality": "COMPLETE", "run_id": run_id or carry.new_run_id(),
                    "shares": shares, "bpt": {{k: 1.0 for k in shares}}}}
        def w(path, rows):
            with open(path, "w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write((r if isinstance(r, str) else json.dumps(r)) + chr(10))
            return path
        D = tempfile.mkdtemp()
    """) + textwrap.dedent(body)
    p = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, timeout=300)
    return p.returncode == 0, (p.stdout + p.stderr)[-400:]


def mutant(pairs):
    """A throwaway copy of tools/ with `pairs` applied. Each replacement must match exactly once,
    so a mutation that silently stopped applying is a hard error rather than a false PASS."""
    d = tempfile.mkdtemp(prefix="sw-mut-")
    dst = os.path.join(d, "tools")
    shutil.copytree(TOOLS, dst)
    for fname, old, new in pairs:
        q = os.path.join(dst, fname)
        s = open(q, encoding="utf-8").read()
        assert s.count(old) == 1, f"pola mutasi tak unik di {fname}: {old[:60]!r}"
        open(q, "w", encoding="utf-8").write(s.replace(old, new))
    return dst


# --------------------------------------------------------------------------- the invariants
CASES = [
    # ---------------------------------------------------------------- SW-1303 partial evidence
    ("bukti parsial di HISTORY tetap menutup promosi",
     [("optimize.py",
       "    qs = [quality_of(r) for r in (comparable_records or [])]",
       "    qs = []")],
     """
     recs = [rec(1000 + i*86400*7, {"Bash": 20.0 + i*9, "Read": 80.0 - i*9}) for i in range(9)]
     for r in recs: r["evidence_quality"] = "PARTIAL"
     keep, _ = optimize.comparable(recs)
     q = optimize.effective_quality(None, keep)
     assert q == "PARTIAL", f"kualitas history diabaikan: {q}"
     assert not optimize.emittable(q, False), "bukti PARTIAL lolos tanpa --accept-partial"
     """),

    ("live COMPLETE tak boleh menutupi history PARTIAL",
     [("optimize.py",
       '    if live:\n        qs.append(live.get("quality") or "UNKNOWN")\n    return worst_quality(qs)',
       '    if live:\n        return live.get("quality") or "UNKNOWN"\n    return worst_quality(qs)')],
     """
     recs = [rec(1000 + i*86400*7, {"Bash": 20.0 + i*9, "Read": 80.0 - i*9}) for i in range(9)]
     for r in recs: r["evidence_quality"] = "PARTIAL"
     keep, _ = optimize.comparable(recs)
     q = optimize.effective_quality(acc(quality="COMPLETE"), keep)
     assert q == "PARTIAL", f"sweep live yang lengkap menutupi history parsial: {q}"
     """),

    ("evidence_quality yang HILANG bukan COMPLETE",
     [("optimize.py", '    q = rec.get("evidence_quality")\n    return q if isinstance(q, str) and q in QUALITY_RANK else "UNKNOWN"\n', '    q = rec.get("evidence_quality")\n    return q if isinstance(q, str) and q in QUALITY_RANK else "COMPLETE"\n')],
     """
     # Schema 2 DECLARES that it records quality, lalu tidak mencantumkannya. Hanya bentuk ini
     # yang sampai ke default nilai-hilang; schema 0/1 sudah dijegal lebih dulu oleh gerbang skema,
     # jadi memakai schema 1 di sini membuat mutan tetap HIJAU dan invariannya tak terjaga.
     assert optimize.quality_of({"schema_version": 2}) == "UNKNOWN", \
         "record schema-2 tanpa evidence_quality dibaca COMPLETE"
     assert not optimize.emittable(optimize.quality_of({"schema_version": 2}), False), \
         "record tanpa kualitas dipromosikan"
     """),

    ("INVALID tidak pernah disahkan oleh --accept-partial",
     [("optimize.py",
       '    return quality == "COMPLETE" or (quality == "PARTIAL" and bool(accept_partial))',
       '    return quality == "COMPLETE" or bool(accept_partial)')],
     """
     assert not optimize.emittable("INVALID", True), "INVALID lolos lewat --accept-partial"
     assert not optimize.emittable("UNKNOWN", True), "UNKNOWN lolos lewat --accept-partial"
     assert optimize.emittable("PARTIAL", True), "PARTIAL yang diterima justru ditolak"
     """),

    ("kandidat dari bukti parsial tetap membawa penandanya",
     [("optimize.py",
       "effective_evidence_quality: {f.get('effective_evidence_quality', 'UNKNOWN')}\n"
       "partial_evidence_accepted: {str(bool(f.get('partial_evidence_accepted'))).lower()}\n",
       "")],
     """
     f = optimize.finding("x", "CANDIDATE", "h", "e", scope="s")
     f["effective_evidence_quality"] = "PARTIAL"; f["partial_evidence_accepted"] = True
     t = optimize.spec_text(f)
     assert "effective_evidence_quality: PARTIAL" in t, "provenance kualitas hilang dari kandidat"
     assert "partial_evidence_accepted: true" in t, "penanda penerimaan hilang dari kandidat"
     """),

    ("schema 0/1 tak bisa menyatakan kualitas yang ia dahului",
     [("optimize.py",
       "    if schema < SCHEMA_WITH_QUALITY:\n        return \"UNKNOWN\"",
       "    if False:\n        return \"UNKNOWN\"")],
     """
     assert optimize.quality_of({"schema_version": 1, "evidence_quality": "COMPLETE"}) == "UNKNOWN", \
         "record schema-1 dipercaya menyatakan COMPLETE"
     """),

    ("retry dgn sapuan lebih buruk tidak mencuci provenance",
     [("optimize.py",
       "                if worse != quality_of(kept):",
       "                if False:")],
     """
     rid = "c"*32
     a = rec(100, {"Bash": 50.0, "Read": 50.0}, run_id=rid); a["evidence_quality"] = "COMPLETE"
     b = rec(100, {"Bash": 50.0, "Read": 50.0}, run_id=rid); b["evidence_quality"] = "PARTIAL"
     p = w(os.path.join(D, "retry.jsonl"), [a, b])
     kept, _rej, _n = optimize.load_history(p)
     assert "PARTIAL" in {optimize.quality_of(r) for r in kept}, "kualitas retry yang buruk hilang"
     """),

    ("status tidak boleh bertentangan dgn berkas kandidat yang ditulis",
     [("optimize.py",
       '    if any(f["state"] == "CANDIDATE" for f in findings):\n        return "CANDIDATE"\n    if not emittable(q, accept_partial):',
       '    if not emittable(q, accept_partial):')],
     """
     f = [{"state": "CANDIDATE", "id": "ledger-x"}]
     st = optimize.overall_status(f, {"comparable": []}, None, {}, False, effective="PARTIAL")
     assert st == "CANDIDATE", f"status {st} sementara kandidat tetap ditulis"
     """),

    ("scope isolation: populasi berbeda tak pernah dilebur",
     [("optimize.py",
       """        if scope_of(r) != n_scope:
            dropped.append((r, f"scope {scope_of(r)!r} vs {n_scope!r}"))
            continue""",
       """        if False:
            pass""")],
     """
     recs = [rec(100, {"Bash": 40.0, "Read": 60.0}, scope="a"),
             rec(200, {"Bash": 80.0, "Read": 20.0}, scope="b")]
     keep, _ = optimize.comparable(recs)
     assert len({optimize.scope_of(r) for r in keep}) == 1, "dua scope dilebur jadi satu tren"
     """),

    ("identitas run: dua agen dgn metrik identik = dua pengamatan",
     [("optimize.py", 'rid = r.get("run_id")', 'rid = json.dumps(r.get("shares"), sort_keys=True)')],
     """
     p = w(os.path.join(D, "h.jsonl"), [rec(100, {"Bash": 50.0, "Read": 50.0}),
                                        rec(100, {"Bash": 50.0, "Read": 50.0})])
     recs, rej, _ = optimize.load_history(p)
     assert len(recs) == 2, "populasi menyusut: dua agen dihitung satu"
     """),

    ("fail-closed: bukti PARTIAL tak boleh melahirkan kandidat",
     # Sebelum 1.3.1 mutasi ini menyasar `usable = accept_partial or quality == "COMPLETE"`,
     # yang hanya menjaga jalur LIVE. Sekarang menyasar satu gerbang yang sama untuk live DAN
     # history, dan oracle-nya menguji kedua jalur itu.
     [("optimize.py", "    usable = emittable(quality, accept_partial)", "    usable = True")],
     """
     f = optimize.analyse(acc(quality="PARTIAL"), EMPTY_HIST, None, None, scope="s")
     assert [x["state"] for x in f] == ["OBSERVED"], "kandidat lahir dari sapuan setengah jadi"
     recs = [rec(1000 + i*86400*7, {"Bash": 20.0 + i*9, "Read": 80.0 - i*9}) for i in range(9)]
     for r in recs: r["evidence_quality"] = "PARTIAL"
     keep, dropped = optimize.comparable(recs)
     h = {"comparable": keep, "total": len(recs), "in_scope": len(recs), "rejected": {},
          "dropped": dropped, "time_order": "ok"}
     g = optimize.analyse(None, h, None, None, scope="default")
     assert not [x for x in g if x["state"] == "CANDIDATE"], \
         "kandidat lahir dari history yang seluruhnya PARTIAL"
     """),

    ("candidate_id membawa scope: dua peran tak menabrak satu berkas",
     [("optimize.py",
       'cand_id = f"{cid}-{scope}-{digest(cid, scope, THRESHOLD_SCHEMA_VERSION, bucket)[:8]}"',
       'cand_id = f"{cid}-{digest(cid, THRESHOLD_SCHEMA_VERSION, bucket)[:8]}"')],
     """
     a = optimize.analyse(acc(), EMPTY_HIST, None, None, scope="BUILDER")[0]
     b = optimize.analyse(acc(), EMPTY_HIST, None, None, scope="REVIEWER")[0]
     assert a["candidate_id"] != b["candidate_id"], "dua peran menulis ke kandidat yang sama"
     """),

    ("nol spam usulan: kandidat yang ada tidak ditulis ulang",
     [("optimize.py",
       """        if os.path.exists(p):
            # An artifact written before 1.3.1 carries no evidence provenance, so it may be the""",
       """        if False:
            # An artifact written before 1.3.1 carries no evidence provenance, so it may be the""")],
     """
     f = optimize.analyse(acc(), EMPTY_HIST, None, None, scope="x")[0]
     out = os.path.join(D, "c")
     optimize.emit_candidates([f], out)
     w2, e2, _ = optimize.emit_candidates([f], out)
     assert (len(w2), len(e2)) == (0, 1), "penjadwal menulis ulang usulan yang sama tiap siklus"
     """),

    ("baris raksasa: dilewati DAN membuat bukti PARTIAL",
     [("carry.py",
       """        if len(line) > MAX_LINE:              # counted, never silently dropped
            oversize += 1
            continue""",
       """        if False:
            pass""")],
     """
     p = os.path.join(D, "s.jsonl")
     rows = []
     for i in range(60):
         rows.append({"type": "assistant", "version": "2.1.270", "message": {"model": "m",
             "usage": {"input_tokens": 1, "output_tokens": 1},
             "content": [{"type": "tool_use", "id": str(i), "name": "Bash", "input": {}}]}})
         rows.append({"type": "user", "message": {"content": [
             {"type": "tool_result", "tool_use_id": str(i), "content": "ok"}]}})
     w(p, rows)
     with open(p, "a", encoding="utf-8") as fh:
         fh.write(json.dumps({"type": "user", "message": {"content": [
             {"type": "tool_result", "tool_use_id": "b",
              "content": "A" * (carry.MAX_LINE + 10)}]}}) + chr(10))
     a = carry.accumulate([p], min_turns=1)
     assert a["oversize"] == 1 and a["quality"] == "PARTIAL", (a["oversize"], a["quality"])
     """),

    ("reentrancy: penjadwal kedua ditolak, tak menulis bersamaan",
     [("optimize.py",
       "        except FileExistsError:\n            return False",
       "        except FileExistsError:\n            return True")],
     """
     lk = os.path.join(D, "l.lock")
     with optimize.Lock(lk) as first:
         assert first is True
         with optimize.Lock(lk) as second:
             assert second is False, "dua penjadwal menulis kandidat bersamaan"
     """),

    ("append pasca-crash: record baru tak dilem ke baris yang robek",
     [("carry.py",
       """            fh.seek(0, os.SEEK_END)
            if fh.tell():
                fh.seek(fh.tell() - 1)
                if fh.read(1) != "\\n":
                    fh.write("\\n")""",
       "            pass")],
     """
     p = os.path.join(D, "h.jsonl")
     with open(p, "w", encoding="utf-8") as fh:
         fh.write(json.dumps(rec(100, {"Bash": 50.0, "Read": 50.0})) + chr(10))
         fh.write('{"schema_version": 2, "record_ty')          # mati di tengah baris
     a = {"sessions": 40, "turns": 1000, "lengths": [10]*40,
          "carry": collections.Counter({"Bash": 60, "Read": 40}),
          "size": {"Bash": 1, "Read": 1}, "usage": collections.Counter(),
          "runtimes": {}, "models": {}, "unreadable": 0, "oversize": 0,
          "skipped_by_limit": 0, "scanned": 40, "short": 0, "quality": "COMPLETE"}
     carry.history(p, a, 100, scope_id="s")
     recs, _, _ = optimize.load_history(p)
     assert len(recs) == 2, "crash memakan DUA record: yang robek dan yang berikutnya"
     """),

    ("label tak dipercaya dibersihkan sebelum mencapai terminal",
     [("carry.py", '    src = SAFE_LABEL.sub("", str(src))[:64] or "(unnamed)"',
       '    src = str(src)')],
     """
     out = carry.bucket("attach:" + chr(27) + "[31mhook" + chr(7))
     assert chr(27) not in out and chr(7) not in out, "byte kendali lolos ke laporan"
     """),

    ("identitas tren stabil: jendela membesar bukan usulan baru",
     [("optimize.py", "                                   bucket=1 if per_month > 0 else -1,",
       "                                   bucket=bucket_of(abs(per_month)),")],
     """
     # Deret harus NAIK lalu MENDATAR. Deret linier sempurna punya kemiringan yang sama di
     # jendela mana pun, jadi ia tak bisa membedakan identitas-dari-arah dari
     # identitas-dari-besaran: fixture degenerat yang membuat mutan lolos.
     def hist_of(n):
         rows = []
         for i in range(n):
             share = 30.0 + min(i, 3) * 12.0        # naik 4 titik, lalu datar
             rows.append(rec(100 + i*86400*7, {"Bash": share, "Read": 100.0 - share}, scope="t"))
         return {"comparable": rows, "total": n, "in_scope": n, "rejected": {}, "dropped": [],
                 "time_order": "ok"}
     ids = set()
     for n in (4, 6, 8, 10, 12):
         f = [x for x in optimize.analyse(None, hist_of(n), None, None, scope="t")
              if x["id"] == "trend-bash"]
         if f:
             ids.add(f[0]["candidate_id"])
     assert len(ids) == 1, f"penaksir yang mengendap mencetak {len(ids)} usulan utk satu gerakan"
     """),

    ("cermin share: satu gerakan tidak dilaporkan dua kali",
     [("optimize.py", "            if mirror:\n", "            if False:\n")],
     """
     rows = [rec(100 + i*86400*7, {"Bash": 30.0 + i*8.0, "Read": 70.0 - i*8.0}, scope="t")
             for i in range(6)]
     h = {"comparable": rows, "total": 6, "in_scope": 6, "rejected": {}, "dropped": [],
          "time_order": "ok"}
     tr = [x for x in optimize.analyse(None, h, None, None, scope="t")
           if x["id"].startswith("trend-")]
     assert len(tr) == 1, f"{len(tr)} kandidat tren untuk satu gerakan komplementer"
     """),

    ("tren: kemiringan adalah sinyal, z hanya menandai lonjakan",
     [("optimize.py",
       '            if t and abs(t["slope"] * 30.0) >= TREND_MIN_SLOPE:',
       '            if t and abs(t["slope"] * 30.0) >= TREND_MIN_SLOPE and abs(t["z"]) >= TREND_MIN_Z:')],
     """
     rows = [rec(100 + i*86400*7, {"Bash": 30.0 + i*8, "Read": 70.0 - i*8}, scope="s")
             for i in range(6)]
     hist = {"comparable": rows, "total": 6, "in_scope": 6, "rejected": {}, "dropped": [],
             "time_order": "ok"}
     f = optimize.analyse(None, hist, None, None, scope="s")
     assert any(x["id"].startswith("trend-") for x in f), \\
         "kenaikan linier bersih tak terlihat: konjungsi slope AND z hanya melaporkan lonjakan"
     """),
]


def main():
    print(f"  (setiap kasus: mutasi -> harus MERAH, sumber asli -> harus HIJAU)\n")
    for label, pairs, body in CASES:
        try:
            md = mutant(pairs)
        except AssertionError as e:
            global F
            F += 1
            print(f"  FAIL  {label}: mutasi tak bisa dipasang — {e}")
            continue
        mut_holds, mut_out = oracle(md, body)
        real_holds, real_out = oracle(TOOLS, body)
        shutil.rmtree(os.path.dirname(md), ignore_errors=True)
        report(label, not mut_holds, real_holds, (real_out if not real_holds else mut_out).strip()[-200:])
    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
