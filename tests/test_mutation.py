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
        import evidence_acquire, evidence_history
        from evidence.absence import Absence
        from evidence.container import history_integrity
        from evidence.values import make_epoch, make_scope_id
        import time as _t
        def facts(i=0, sources=1, counters=None, parsed=None, bound=0, carry_map=None):
            files = parsed if parsed is not None else {{
                "/x/%d/%d.jsonl" % (i, k): {{"content": "%064x" % (i * 10 + k), "turns": 10}}
                for k in range(sources)}}
            ident = {{path: {{"dev": 1, "inode": 100 + k, "size": 10, "mtime_ns": 1}}
                     for k, path in enumerate(sorted(files))}}
            base = {{"discovered": sources, "skipped_by_limit": 0, "unreadable": 0, "oversize": 0,
                    "identity_changed": 0, "empty_source": 0, "not_attempted": 0, "malformed": 0,
                    "records_rejected": 0, "dirs_unreadable": 0}}
            base.update(counters or {{}})
            return {{"sessions": 40, "turns": 1000 + i, "lengths": [10] * 40,
                    "carry": collections.Counter(carry_map or {{"Bash": 60, "Read": 40}}),
                    "size": {{"Bash": 1, "Read": 1}}, "usage": collections.Counter(),
                    "runtimes": {{}}, "models": {{}}, "unreadable": 0, "oversize": 0,
                    "skipped_by_limit": 0, "scanned": sources, "short": 0, "quality": "COMPLETE",
                    "sources": ident, "parsed": files, "sample_bound": bound,
                    "counters": base}}
        def state_of(f, when=None):
            r = evidence_acquire.observation(f, "s", "", "1.4.0", 0, Absence.KNOWN_ABSENT,
                                             when or int(_t.time()))
            return evidence_acquire.state_of(r, when or int(_t.time()))
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
     [("optimize.py", 'usable = accept_partial or quality == "COMPLETE"', "usable = True")],
     """
     f = optimize.analyse(acc(quality="PARTIAL"), EMPTY_HIST, None, None, scope="s")
     assert [x["state"] for x in f] == ["OBSERVED"], "kandidat lahir dari sapuan setengah jadi"
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
            existing.append(f["candidate_id"])
            continue""",
       """        if False:
            pass""")],
     """
     f = optimize.analyse(acc(), EMPTY_HIST, None, None, scope="x")[0]
     out = os.path.join(D, "c")
     optimize.emit_candidates([f], out)
     w2, e2, _ = optimize.emit_candidates([f], out)
     assert (len(w2), len(e2)) == (0, 1), "penjadwal menulis ulang usulan yang sama tiap siklus"
     """),

    ("baris raksasa: dilewati DAN membuat bukti PARTIAL",
     [("carry.py",
       """        if len(raw) > MAX_LINE:               # counted, never silently dropped
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
     [("evidence_history.py",
       """            handle.seek(0, os.SEEK_END)
            if handle.tell():
                handle.seek(handle.tell() - 1)
                if handle.read(1) != "\\n":
                    handle.write("\\n")
                handle.seek(0, os.SEEK_END)""",
       "            pass")],
     """
     p = os.path.join(D, "h.jsonl")
     carry.history(p, facts(1), 100, scope_id="s")
     with open(p, "a", encoding="utf-8") as fh:
         fh.write('{"envelope": {"schema_ver')                 # mati di tengah baris
     carry.history(p, facts(2), 100, scope_id="s")
     c = evidence_history.read_container(p)
     assert len(c.records) == 2, ("crash memakan DUA record", len(c.records))
     """),

    # ---------------------------------------------------------------- v1.4 integration
    ("BOUNDED tidak boleh terbaca sebagai INTACT",
     [("evidence/certificate.py",
       "    if cert.skipped_by_limit > 0:\n        return AcquisitionIntegrity.BOUNDED",
       "    if False:\n        return AcquisitionIntegrity.BOUNDED")],
     """
     f = facts(1, counters={"skipped_by_limit": 3, "discovered": 4}, bound=1)
     assert state_of(f).derived.value == "BOUNDED", state_of(f).derived.value
     """),

    ("DEGRADED tidak boleh lolos sebagai bounded yang diterima",
     [("evidence/promotion.py",
       "    allowed = ACCEPTABLE_WITH_FLAG if accept_bounded else ACCEPTABLE_WITHOUT_FLAG\n"
       "    allowed = tuple(state for state in allowed if state in contract.acquisition_integrity)",
       "    allowed = tuple(AcquisitionIntegrity)")],
     """
     from evidence.domains import AcquisitionIntegrity, AnalysisSufficiency, ContainerIntegrity
     from evidence.domains import WorldState
     from evidence.promotion import promotable
     from evidence.registry import dependency_contract
     c = dependency_contract("listing_cost")
     assert promotable(c, AcquisitionIntegrity.DEGRADED, ContainerIntegrity.INTACT,
                       AnalysisSufficiency.SUFFICIENT, True, WorldState.SINGLE_WORLD,
                       True) is False, "kehilangan tak terduga diterima sebagai batas yang dipilih"
     """),

    ("penghitung akuisisi yang hilang tidak boleh jadi nol diam-diam",
     [("evidence_acquire.py",
       '    counters = {name: int(facts["counters"].get(name, 0)) for name in',
       '    counters = {name: int(facts["counters"].get(name, 0) if name != "unreadable" else 0)\n                for name in')],
     """
     f = facts(1, counters={"unreadable": 2, "discovered": 3})
     f["sources"]["/x/1/ghost.jsonl"] = {"dev": 1, "inode": 9, "size": 1, "mtime_ns": 1}
     f["sources"]["/x/1/ghost2.jsonl"] = {"dev": 1, "inode": 8, "size": 1, "mtime_ns": 1}
     st = state_of(f)
     assert st.derived.value == "DEGRADED", (st.derived.value, [r.value for r in st.reasons])
     """),

    ("record generasi lama tidak boleh jadi record generasi ini",
     [("evidence_history.py",
       "        return \"current\", decode_record(raw)\n    except WireError:\n"
       "        return \"legacy\", _legacy_record(raw)",
       "        return \"current\", decode_record(raw)\n    except WireError:\n"
       "        return \"current\", _legacy_record(raw)")],
     """
     p = os.path.join(D, "h.jsonl")
     w(p, [rec(100, {"Bash": 50.0, "Read": 50.0})])            # satu record skema 2
     c = evidence_history.read_container(p)
     assert (len(c.records), len(c.legacy)) == (0, 1), (len(c.records), len(c.legacy))
     st = history_integrity(c, Absence.KNOWN_ABSENT, make_scope_id("default"),
                            make_epoch(int(_t.time())))
     assert st.integrity.value == "UNVERIFIED", st.integrity.value
     """),

    ("baris history yang rusak tidak boleh menghilang",
     [("evidence_history.py",
       "            except Exception:\n"
       "                rejections.append(make_rejection(index, (Reason.LINE_UNPARSEABLE,)))",
       "            except Exception:\n                pass")],
     """
     p = os.path.join(D, "h.jsonl")
     carry.history(p, facts(1), 100, scope_id="s")
     with open(p, "a", encoding="utf-8") as fh:
         fh.write("{not json" + chr(10))
     c = evidence_history.read_container(p)
     st = history_integrity(c, Absence.KNOWN_ABSENT, make_scope_id("s"),
                            make_epoch(int(_t.time())))
     assert c.lines_rejected == 1 and st.integrity.value != "INTACT", (c.lines_rejected,
                                                                      st.integrity.value)
     """),

    ("sweep gagal ditulis sebagai TOMBSTONE, bukan diam",
     [("evidence_acquire.py",
       '    if facts["parsed"]:\n        return make_carry_sweep(envelope, payload_for(facts, when), certificate)',
       '    if True:\n        return make_carry_sweep(envelope, payload_for(facts, when), certificate)')],
     """
     f = facts(1, parsed={}, counters={"unreadable": 1, "discovered": 1})
     f["sources"] = {"/x/1/gone.jsonl": {"dev": 1, "inode": 9, "size": 1, "mtime_ns": 1}}
     f["carry"] = collections.Counter()
     f["turns"] = f["sessions"] = 0
     r = evidence_acquire.observation(f, "s", "", "1.4.0", 0, Absence.KNOWN_ABSENT,
                                      int(_t.time()))
     assert type(r).__name__ == "CarrySweepFailed", type(r).__name__
     assert evidence_acquire.state_of(r, int(_t.time())).derived.value == "FAILED"
     """),

    ('workload_class "" tetap sah',
     [("evidence/values.py",
       '    _require(f.is_str(text), reason, field,\n             "a string; the empty string is a valid workload class")',
       '    _require(f.is_str(text) and text != "", reason, field,\n             "a string; the empty string is a valid workload class")')],
     """
     p = os.path.join(D, "h.jsonl")
     carry.history(p, facts(1), 100, scope_id="s", workload_class="")
     c = evidence_history.read_container(p)
     assert len(c.records) == 1, "workload_class kosong menolak record yang sah"
     """),

    ("host_profile_id tidak boleh mengubah semantik finding yang dipertahankan",
     [("evidence/decision.py",
       "    worlds = {certificate_world_id(m.certificate, scope) for m in members}",
       "    worlds = {(certificate_world_id(m.certificate, scope),\n               m.certificate.host_profile_id) for m in members}")],
     """
     from evidence.decision import population_for, world_state
     p = os.path.join(D, "h.jsonl")
     carry.history(p, facts(1), 100, scope_id="s")
     carry.history(p, facts(2), 100, scope_id="s")
     rows = [json.loads(l) for l in open(p, encoding="utf-8").read().splitlines() if l.strip()]
     rows[1]["certificate"]["host_profile_id"] = "0" * 16      # a second host, same everything
     w(p, [rows[0], rows[1]])
     c = evidence_history.read_container(p)
     pop = population_for(c, make_scope_id("s"), evidence_acquire.make_workload_id(""))
     hosts = {m.certificate.host_profile_id.hex for m in pop.members}
     assert len(hosts) == 2, hosts
     assert world_state(pop.members, make_scope_id("s")).value == "SINGLE_WORLD", "host memecah dunia"
     """),

    ("dict mentah tidak boleh sampai ke algoritma bukti",
     [("wire/parse.py",
       "    if unknown:\n        raise WireError(reason, path, \"unknown member %s\" % sorted(unknown))",
       "    if False:\n        raise WireError(reason, path, \"unknown member %s\" % sorted(unknown))")],
     """
     p = os.path.join(D, "h.jsonl")
     carry.history(p, facts(1), 100, scope_id="s")
     raw = json.loads(open(p, encoding="utf-8").read().splitlines()[0])
     raw["envelope"]["surprise"] = 1
     w(p, [raw])
     c = evidence_history.read_container(p)
     assert len(c.records) == 0 and c.lines_rejected == 1, (len(c.records), c.lines_rejected)
     """),

    ("optimizer 1.3 tidak boleh membaca skema generasi ini",
     [("optimize.py", "    if isinstance(o.get(\"envelope\"), dict):", "    if False:"),
      ("optimize.py", "SCHEMA_SUPPORTED = (0, 1, 2)", "SCHEMA_SUPPORTED = (0, 1, 2, 4)"),
      ("optimize.py", '    sh = o.get("shares")',
       '    sh = o.get("shares") or (o.get("payload") or {}).get("shares")'),
      ("optimize.py", '    sv = o.get("schema_version", 0)',
       '    sv = o.get("schema_version", (o.get("envelope") or {}).get("schema_version", 0))')],
     """
     p = os.path.join(D, "h.jsonl")
     carry.history(p, facts(1), 100, scope_id="s")
     recs, rej, _ = optimize.load_history(p)
     assert (len(recs), sum(rej.values())) == (0, 1), (len(recs), dict(rej))
     """),

    ("kanari privasi tidak boleh tersalin ke history",
     [("evidence_acquire.py",
       '    return hashlib.sha256(os.path.abspath(path).encode("utf-8", "surrogateescape")).hexdigest()[:12]',
       '    return path')],
     """
     p = os.path.join(D, "h.jsonl")
     f = facts(1, parsed={"/home/secret-canary/AKIA1234567890/t.jsonl":
                          {"content": "%064x" % 7, "turns": 10}})
     f["sources"] = {"/home/secret-canary/AKIA1234567890/t.jsonl":
                     {"dev": 1, "inode": 1, "size": 1, "mtime_ns": 1}}
     carry.history(p, f, 100, scope_id="s")
     raw = open(p, encoding="utf-8").read()
     assert "secret-canary" not in raw and "AKIA1234567890" not in raw, "path bocor ke history"
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
    # --------------------------------------------------- review A: the six port defects it found
    ("sweep gagal harus menulis tombstone, bukan diam",
     [("carry.py", "    if args.history:",
       "    if args.history and sum(a[\"carry\"].values()):")],
     """
     import subprocess
     d = tempfile.mkdtemp()
     src = os.path.join(d, "t.jsonl")
     open(src, "w").write(chr(123) + '"type":"assistant"' + chr(125) + chr(10))
     os.chmod(src, 0)                                  # nothing readable: the sweep FAILS
     h = os.path.join(d, "h.jsonl")
     subprocess.run([sys.executable, os.path.join(os.path.dirname(carry.__file__), "carry.py"),
                     src, "--history", h], capture_output=True, text=True)
     assert os.path.exists(h), "sweep gagal tidak menulis apa pun"
     c = evidence_history.read_container(h)
     assert len(c.records) == 1, len(c.records)
     assert type(c.records[0]).__name__ == "CarrySweepFailed", type(c.records[0]).__name__
     """),

    ("record yang hilang tertangkap rantai (bukan dengan menghitung baris kosong)",
     [("evidence/container.py",
       "        if broken:\n            r.fault(Reason.CHAIN_BROKEN, ContainerIntegrity.DEGRADED)",
       "        if False:\n            pass")],
     """
     p = os.path.join(D, "h.jsonl")
     for i in range(3):
         carry.history(p, facts(i + 1), 100, scope_id="s")
     rows = open(p, encoding="utf-8").read().splitlines()
     open(p, "w", encoding="utf-8").write(rows[0] + chr(10) + chr(10) + rows[2] + chr(10))
     st = history_integrity(evidence_history.read_container(p), Absence.KNOWN_ABSENT,
                            make_scope_id("s"), make_epoch(int(_t.time())))
     assert st.integrity.value == "DEGRADED", st.integrity.value
     assert "chain_broken" in [r.value for r in st.reasons], [r.value for r in st.reasons]
     """),

    ("path yang lenyap sebelum identitasnya dibekukan tak boleh merusak akuntansi",
     [("carry.py",
       '            unreadable += 1\n            vanished += 1\n            continue',
       "            unreadable += 1\n            continue")],
     """
     d = tempfile.mkdtemp()
     a = carry.accumulate([os.path.join(d, "vanished.jsonl")], 1)
     s = state_of(a)
     assert s.derived.value == "DEGRADED", (s.derived.value, [r.value for r in s.reasons])
     assert [r.value for r in s.reasons] == ["discovery_incomplete"], [r.value for r in s.reasons]
     """),

    ("byte non-UTF-8 dalam record tak boleh diperbaiki diam-diam",
     [("evidence_history.py",
       '        handle = open(path, "rb")               # bytes: a decoding fault is evidence, not a repair',
       '        handle = open(path, encoding="utf-8", errors="replace")')],
     """
     p = os.path.join(D, "h.jsonl")
     carry.history(p, facts(1), 100, scope_id="s")
     raw = open(p, "rb").read()
     key = b'"writer_version": "'                      # a free string value in the record
     i = raw.find(key) + len(key)
     assert i > len(key) and raw[i:i + 1] != b'"', raw[:80]
     open(p, "wb").write(raw[:i] + bytes([255]) + raw[i + 1:])
     c = evidence_history.read_container(p)
     st = history_integrity(c, Absence.KNOWN_ABSENT, make_scope_id("s"),
                            make_epoch(int(_t.time())))
     assert (len(c.records), c.lines_rejected) == (0, 1), (len(c.records), c.lines_rejected)
     assert st.integrity.value == "DEGRADED", st.integrity.value
     """),

    ("sumber kosong bukan sumber ter-parse",
     [("carry.py",
       '            empty_source += 1\n            continue\n        parsed_files[p] = '
       '{"content": meta["content"], "turns": N}',
       '            empty_source += 1\n        parsed_files[p] = '
       '{"content": meta["content"], "turns": N}')],
     """
     d = tempfile.mkdtemp()
     open(os.path.join(d, "e.jsonl"), "w").close()     # readable, and it holds no turn at all
     a = carry.accumulate([os.path.join(d, "e.jsonl")], 1)
     assert a["counters"]["empty_source"] == 1, a["counters"]
     assert len(a["parsed"]) == 0, a["parsed"]
     s = state_of(a)
     assert s.derived.value == "FAILED", s.derived.value
     """),

    ("tanpa lock, jangan menulis",
     [("evidence_history.py",
       '            return False, "history lock unavailable — not written"',
       "            pass")],
     """
     import errno, fcntl
     p = os.path.join(D, "h.jsonl")
     real = fcntl.flock
     fcntl.flock = lambda *a, **k: (_ for _ in ()).throw(OSError(errno.ENOLCK, "no locks"))
     try:
         ok, note = evidence_history.append_chained(
             p, lambda seq, prev: evidence_acquire.encoded(
                 evidence_acquire.observation(facts(1), "s", "", "1.4.0", seq, prev,
                                              int(_t.time()))),
             make_scope_id("s"))
     finally:
         fcntl.flock = real
     assert ok is False, "record ditulis tanpa serialisasi"
     assert (not os.path.exists(p)) or open(p).read() == "", open(p).read()[:120]
     """),

    ("generasi yang tak pernah ditulis repo ini tak boleh jadi pembanding",
     [("evidence_history.py",
       "                try:\n                    _legacy_record(raw)\n"
       "                except WireError:\n                    continue\n",
       "                if False:\n                    pass\n")],
     """
     p = os.path.join(D, "h.jsonl")
     w(p, [{"schema_version": 99, "record_type": "carry_run", "ts": 1, "turns": 10,
            "scope_id": "s", "shares": {"Bash": 100.0}}])
     assert evidence_history.read_views(p) == [], evidence_history.read_views(p)
     c = evidence_history.read_container(p)
     assert c.lines_rejected == 1, c.lines_rejected
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
