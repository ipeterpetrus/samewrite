#!/usr/bin/env python3
"""Phase 2: the production port of the frozen v1.4 evidence kernel.

What this file proves, in the order the integration was built:

  PORT        the kernel in tools/evidence and tools/wire is the frozen one, byte for byte.
  PRODUCER    carry.py emits TYPED evidence through the frozen constructors, never a hand-made
              current-schema dict, and what it writes is what the decoder accepts.
  BOUNDED     an intentional `--max-files` bound is BOUNDED; an unexpected loss is DEGRADED, and
              no flag converts the second into the first.
  FAILED      a sweep that read nothing is a tombstone: it cannot delete history, cannot vanish,
              and cannot leave stale INTACT evidence standing as current truth.
  CONTAINER   container integrity is global — a malformed line is damage even when every other
              record parses.
  LEGACY      this repository's own generations (0, 1, 2) are read, attributed, and never
              granted current trust.
  ISOLATION   the 1.3 optimizer cannot consume a current-generation record.
  PRIVACY     five canary classes, every Phase-2 sink, zero leaks, with a positive control.
  OFFLINE     no network, no model, in the acquisition and evidence paths.
  SHADOW      what each retained finding WOULD see, computed without writing an artifact.

The privacy canaries are unique STRINGS, deliberately not shaped like real credentials: a test
file that carries a real key shape is itself the leak its repository guards against.

Standalone: run this file."""
import ast
import collections
import errno
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
FROZEN = "/home/ubuntu/.cache/sw-design/simplified"
sys.path.insert(0, TOOLS)

import carry                                                            # noqa: E402
import evidence_acquire                                                 # noqa: E402
import evidence_history                                                 # noqa: E402
import optimize                                                         # noqa: E402
from evidence.absence import Absence                                    # noqa: E402
from evidence.certificate import evaluate_observation                   # noqa: E402
from evidence.container import history_integrity                        # noqa: E402
from evidence.decision import (make_sufficiency_facts, population_for, sufficiency,
                               world_state)                             # noqa: E402
from evidence.domains import (AcquisitionIntegrity, AnalysisSufficiency, ContainerIntegrity,
                              WorldState)                               # noqa: E402
from evidence.observation import freshness_ok, newest_observation       # noqa: E402
from evidence.promotion import promotable                               # noqa: E402
from evidence.records import RECORD_SCHEMA_VERSION                      # noqa: E402
from evidence.registry import FINDING_FLOORS, dependency_contract       # noqa: E402
from evidence.values import (make_epoch, make_finding_id, make_scope_id,
                             make_workload_id)                          # noqa: E402
from wire.record import decode_record                                   # noqa: E402

P = F = 0
CANARIES = {
    "prompt": "CANARY-PROMPT-please-refactor-the-billing-module",
    "path": "/home/canary-user/Documents/Q3-payroll/secret-canary-dir",
    "secret": "CANARY-CREDENTIAL-" + "PLACEHOLDER-0007",
    "tool_result": "CANARY-TOOL-RESULT-rows: 42 customers exported",
    "name": "Canary McCustomerface",
}
FROZEN_KERNEL_SHA256 = "88e4b48486eaa2a72abcdc4e52542113834e3c96bf08777fd67d13ac1adb82fd"


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print("  PASS  " + label)
    else:
        F += 1
        print("  FAIL  %s: dapat %r, harap %r" % (label, got, want))


def facts(i=1, sources=1, counters=None, parsed=None, bound=0, carry_map=None, turns=1000,
          sessions=40):
    """Acquisition facts in the shape accumulate() returns."""
    files = parsed if parsed is not None else {
        "/x/%d/%d.jsonl" % (i, k): {"content": "%064x" % (i * 10 + k), "turns": 10}
        for k in range(sources)}
    ident = {path: {"dev": 1, "inode": 100 + k, "size": 10, "mtime_ns": 1}
             for k, path in enumerate(sorted(files))}
    base = {"discovered": sources, "skipped_by_limit": 0, "unreadable": 0, "oversize": 0,
            "identity_changed": 0, "empty_source": 0, "not_attempted": 0, "malformed": 0,
            "records_rejected": 0, "dirs_unreadable": 0}
    base.update(counters or {})
    return {"sessions": sessions, "turns": turns, "lengths": [10] * 40,
            "carry": collections.Counter(carry_map or {"Bash": 60, "Read": 40}),
            "size": {"Bash": 1, "Read": 1}, "usage": collections.Counter(), "runtimes": {},
            "models": {}, "unreadable": 0, "oversize": 0, "skipped_by_limit": 0,
            "scanned": sources, "short": 0, "quality": "COMPLETE",
            "sources": ident, "parsed": files, "sample_bound": bound, "counters": base}


def observe(f, when=None, scope="s", workload="", seq=0, prev=Absence.KNOWN_ABSENT):
    when = when or int(time.time())
    return evidence_acquire.observation(f, scope, workload, "1.4.0", seq, prev, when)


def transcript(path, turns=4, body="x" * 100):
    rows = [json.dumps({"type": "assistant", "version": "2.1.270",
                        "message": {"model": "m", "usage": {"output_tokens": 1},
                                    "content": [{"type": "text", "text": body}]}})
            for _ in range(turns)]
    open(path, "w", encoding="utf-8").write("\n".join(rows) + "\n")
    return path


def imports_of(path):
    names = []
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def main():
    now = int(time.time())
    d = tempfile.mkdtemp(prefix="sw-phase2-")

    # ---------------------------------------------------------------- PORT
    digest = hashlib.sha256()
    ported = identical = 0
    for package in ("evidence", "wire"):
        for name in sorted(os.listdir(os.path.join(TOOLS, package))):
            if not name.endswith(".py"):
                continue
            here = open(os.path.join(TOOLS, package, name), "rb").read()
            digest.update(here)
            ported += 1
            frozen = os.path.join(FROZEN, package, name)
            if os.path.exists(frozen) and here == open(frozen, "rb").read():
                identical += 1
    check("35 berkas kernel di-port", ported, 35)
    if os.path.isdir(FROZEN):
        check("setiap berkas kernel byte-identik dengan yang beku", identical, 35)
    else:
        # The Phase-1 design tree lives on the machine the freeze happened on, not on a CI
        # runner. Claiming byte-identity against a directory that is not there would be a green
        # test that proved nothing, so the fallback asserts the thing that binds WITHOUT a second
        # copy: the hash of what was ported. One check either way, so the suite's assertion count
        # does not depend on which machine runs it.
        check("pohon beku tak ada di mesin ini — identitas dibuktikan oleh hash kernel",
              digest.hexdigest(), FROZEN_KERNEL_SHA256)
    check("hash kernel = hash beku Phase 1", digest.hexdigest(), FROZEN_KERNEL_SHA256)
    check("skema history generasi ini dibaca dari kontrak", RECORD_SCHEMA_VERSION, 4)
    check("carry menulis skema itu, bukan salinannya", carry.CURRENT_HISTORY_SCHEMA,
          RECORD_SCHEMA_VERSION)
    check("dua finding dipertahankan", sorted(FINDING_FLOORS),
          ["listing_cost", "write_guard_retirement"])

    # ---------------------------------------------------------------- PRODUCER / READER PAIR
    source = transcript(os.path.join(d, "t.jsonl"))
    accumulated = carry.accumulate([source], min_turns=1)
    check("akuisisi menghasilkan identitas sumber", len(accumulated["sources"]), 1)
    check("akuisisi menghasilkan digest isi", len(accumulated["parsed"]), 1)
    record = observe(accumulated, now)
    raw = evidence_acquire.encoded(record)
    check("produser menghasilkan nilai bertipe, bukan dict", type(record).__name__, "CarrySweep")
    back = decode_record(json.loads(json.dumps(raw)))
    check("write -> read -> nilai bertipe: kesetaraan semantik", back, record)
    check("identitas observasi bertahan", back.equivalence(), record.equivalence())
    check("keadaan akuisisi bertahan",
          evaluate_observation(back, make_epoch(now)).derived,
          evaluate_observation(record, make_epoch(now)).derived)
    check("provenance bertahan: host, config, versi penulis",
          (back.certificate.host_profile_id.hex, back.certificate.discovery_config_digest.hex,
           back.certificate.writer_version),
          (record.certificate.host_profile_id.hex,
           record.certificate.discovery_config_digest.hex, record.certificate.writer_version))
    check("input sufficiency bertahan",
          (back.payload.sessions, back.payload.turns, back.payload.carry_bytes),
          (record.payload.sessions, record.payload.turns, record.payload.carry_bytes))
    check("nol field hilang: byte kanonis sama",
          json.dumps(evidence_acquire.encoded(back), sort_keys=True),
          json.dumps(raw, sort_keys=True))
    shuffled = json.loads(json.dumps(raw))
    shuffled["certificate"] = dict(reversed(list(shuffled["certificate"].items())))
    from evidence.canon import encode as canon_encode
    check("urutan member objek bukan bukti",
          canon_encode(decode_record(shuffled).canon()), canon_encode(record.canon()))
    check("manifest = berkas yang benar-benar terbaca",
          len(record.payload.sample_manifest), len(accumulated["parsed"]))

    # ---------------------------------------------------------------- BOUNDED vs DEGRADED
    bounded = observe(facts(2, counters={"discovered": 5, "skipped_by_limit": 4}, bound=1), now)
    check("--max-files = akuisisi BOUNDED yang disengaja",
          evaluate_observation(bounded, make_epoch(now)).derived, AcquisitionIntegrity.BOUNDED)
    for counter in ("unreadable", "malformed", "identity_changed", "dirs_unreadable"):
        # A source that was LOST was still SELECTED: it belongs in frozen_selection, and the
        # accounting law is what says so. A fixture that forgot it would report UNVERIFIED for
        # a reason that has nothing to do with the loss being tested.
        lossy_facts = facts(3, sources=2)
        if counter in ("unreadable", "identity_changed"):
            lossy_facts["sources"]["/x/3/lost.jsonl"] = {"dev": 1, "inode": 7, "size": 1,
                                                         "mtime_ns": 1}
            lossy_facts["counters"]["discovered"] = 3
        lossy_facts["counters"][counter] = 1
        lossy = observe(lossy_facts, now)
        check("kehilangan tak terduga (%s) -> DEGRADED, bukan BOUNDED" % counter,
              evaluate_observation(lossy, make_epoch(now)).derived,
              AcquisitionIntegrity.DEGRADED)
    both_facts = facts(4, sources=2, bound=3)
    both_facts["sources"]["/x/4/lost.jsonl"] = {"dev": 1, "inode": 7, "size": 1, "mtime_ns": 1}
    both_facts["counters"].update({"unreadable": 1, "discovered": 4, "skipped_by_limit": 1})
    both = observe(both_facts, now)
    check("bound DAN kehilangan -> DEGRADED menang",
          evaluate_observation(both, make_epoch(now)).derived, AcquisitionIntegrity.DEGRADED)
    # and a bound that could not have produced the selection is not evidence at all
    impossible = facts(4, sources=2, bound=1)
    impossible["counters"].update({"discovered": 3, "skipped_by_limit": 1})
    check("bound lebih kecil dari seleksi = relasi mustahil, bukan BOUNDED",
          evaluate_observation(observe(impossible, now), make_epoch(now)).derived,
          AcquisitionIntegrity.UNVERIFIED)
    contract = dependency_contract("listing_cost")
    check("BOUNDED tak promosi tanpa penerimaan eksplisit",
          promotable(contract, AcquisitionIntegrity.BOUNDED, ContainerIntegrity.INTACT,
                     AnalysisSufficiency.SUFFICIENT, False, WorldState.SINGLE_WORLD, True), False)
    check("BOUNDED promosi dengan penerimaan eksplisit",
          promotable(contract, AcquisitionIntegrity.BOUNDED, ContainerIntegrity.INTACT,
                     AnalysisSufficiency.SUFFICIENT, True, WorldState.SINGLE_WORLD, True), True)
    check("DEGRADED tak pernah jadi bound yang diterima",
          promotable(contract, AcquisitionIntegrity.DEGRADED, ContainerIntegrity.INTACT,
                     AnalysisSufficiency.SUFFICIENT, True, WorldState.SINGLE_WORLD, True), False)

    # ---------------------------------------------------------------- COMPLETE
    full = observe(facts(5, sources=3, counters={"discovered": 3}), now)
    check("sapuan penuh tanpa kehilangan -> INTACT",
          evaluate_observation(full, make_epoch(now)).derived, AcquisitionIntegrity.INTACT)
    check("INTACT hanya kalau akuntansi sendiri membuktikannya",
          evaluate_observation(observe(facts(6, sources=3, counters={"discovered": 9}), now),
                               make_epoch(now)).derived, AcquisitionIntegrity.UNVERIFIED)
    check("tak ada asersi kualitas yang bisa menimpa keadaan turunan",
          full.certificate.asserted_integrity, Absence.KNOWN_ABSENT)

    # ---------------------------------------------------------------- FAILED SWEEP / TOMBSTONE
    tomb_path = os.path.join(d, "tomb.jsonl")
    carry.history(tomb_path, facts(7, sources=2), 100, scope_id="s")
    dead = facts(8, parsed={}, counters={"unreadable": 2, "discovered": 2})
    dead["sources"] = {"/x/8/a.jsonl": {"dev": 1, "inode": 1, "size": 1, "mtime_ns": 1},
                       "/x/8/b.jsonl": {"dev": 1, "inode": 2, "size": 1, "mtime_ns": 1}}
    dead["carry"] = collections.Counter()
    dead["turns"] = dead["sessions"] = 0
    carry.history(tomb_path, dead, 0, scope_id="s")
    container = evidence_history.read_container(tomb_path)
    check("sapuan gagal tak menghapus history lama", len(container.records), 2)
    check("sapuan gagal tak menghilang diam-diam",
          type(container.records[-1]).__name__, "CarrySweepFailed")
    check("sapuan gagal terbaca sebagai FAILED",
          evaluate_observation(container.records[-1], make_epoch(now)).derived,
          AcquisitionIntegrity.FAILED)
    check("bukti INTACT lama tak lagi mewakili kebenaran sekarang",
          type(newest_observation(container, make_scope_id("s"))).__name__, "CarrySweepFailed")
    check("kesegaran menolak scope yang sapuan terakhirnya gagal",
          freshness_ok(container, make_scope_id("s"), make_epoch(now)), False)

    # ---------------------------------------------------------------- CONTAINER INTEGRITY
    mixed = os.path.join(d, "mixed.jsonl")
    carry.history(mixed, facts(9), 100, scope_id="s")
    with open(mixed, "a", encoding="utf-8") as fh:
        fh.write("{tidak-json\n")
    carry.history(mixed, facts(10), 100, scope_id="s")
    container = evidence_history.read_container(mixed)
    state = history_integrity(container, Absence.KNOWN_ABSENT, make_scope_id("s"),
                              make_epoch(now))
    check("baris rusak = kerusakan container, bukan nol", container.lines_rejected, 1)
    check("record yang selamat tak mencuci container",
          state.integrity is ContainerIntegrity.INTACT, False)
    check("record yang selamat tetap terbaca", len(container.records), 2)

    # ---------------------------------------------------------------- LEGACY MIX
    def legacy_row(schema, scope="s", ts=None):
        row = {"record_type": "carry_run", "ts": ts or now, "sessions": 40, "turns": 1000,
               "carry_bytes": 10 ** 6, "scanned": 10, "shares": {"Bash": 60.0, "Read": 40.0},
               "bpt": {"Bash": 1.0, "Read": 1.0}}
        if schema:
            row["schema_version"] = schema
            row["scope_id"] = scope
            row["run_id"] = "deadbeef" * 4
            row["evidence_quality"] = "COMPLETE"
        return row

    for label, rows, want_current, want_legacy in (
            ("semua generasi ini", [], 2, 0),
            ("semua generasi lama", [legacy_row(0), legacy_row(2)], 0, 2),
            ("campuran generasi", [legacy_row(2)], 2, 1),
            ("lama + rusak", [legacy_row(1), "{tidak-json"], 0, 1)):
        p = os.path.join(d, "mix-%s.jsonl" % label.replace(" ", "-"))
        with open(p, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write((row if isinstance(row, str) else json.dumps(row)) + "\n")
        for i in range(want_current):
            carry.history(p, facts(11 + i), 100, scope_id="s")
        container = evidence_history.read_container(p)
        check("%s: record generasi ini" % label, len(container.records), want_current)
        check("%s: record generasi lama" % label, len(container.legacy), want_legacy)
        state = history_integrity(container, Absence.KNOWN_ABSENT, make_scope_id("s"),
                                  make_epoch(now))
        if want_legacy:
            check("%s: generasi lama -> container UNVERIFIED" % label,
                  state.integrity, ContainerIntegrity.UNVERIFIED)
        else:
            check("%s: nol generasi lama -> container INTACT" % label,
                  state.integrity, ContainerIntegrity.INTACT)

    p = os.path.join(d, "legacy-only.jsonl")
    open(p, "w", encoding="utf-8").write(json.dumps(legacy_row(2)) + "\n")
    container = evidence_history.read_container(p)
    check("record lama: kind TIDAK ditebak", container.legacy[0].kind, Absence.UNVERIFIED)
    check("record lama: posisi TIDAK dikarang", container.legacy[0].run_seq, Absence.UNVERIFIED)
    check("record lama nol bobot sebagai bukti generasi ini",
          len(population_for(container, make_scope_id("s"), make_workload_id("")).members), 0)

    p = os.path.join(d, "broken-current.jsonl")
    carry.history(p, facts(13), 100, scope_id="s")
    row = json.loads(open(p, encoding="utf-8").read().splitlines()[0])
    row["envelope"]["surprise"] = 1
    open(p, "w", encoding="utf-8").write(json.dumps(row) + "\n")
    container = evidence_history.read_container(p)
    check("record generasi ini yang rusak = kerusakan, bukan 'generasi lama'",
          (len(container.records), len(container.legacy), container.lines_rejected), (0, 0, 1))

    # ---------------------------------------------------------------- OPTIMIZER ISOLATION
    p = os.path.join(d, "iso.jsonl")
    carry.history(p, facts(14), 100, scope_id="s")
    records, rejected, _lines, _ep = optimize.load_history(p)
    check("optimizer 1.3 tak menerima satu pun record generasi ini", len(records), 0)
    check("penolakannya terhitung, bukan senyap", sum(rejected.values()), 1)
    check("penolakannya menyebut skema",
          any("schema_version" in reason for reason in rejected), True)
    check("optimizer 1.3 tetap pada generasi yang ia kenal", optimize.SCHEMA_SUPPORTED, (0, 1, 2))

    # ---------------------------------------------------------------- PRIVACY
    leak_dir = os.path.join(d, "canary")
    os.makedirs(leak_dir)
    canary_path = os.path.join(leak_dir, "secret-canary-dir.jsonl")
    rows = []
    for i in range(4):                        # more than one turn: carry is size x turns REMAINING
        rows.append(json.dumps({"type": "assistant", "version": "2.1.270",
                                "message": {"model": "m", "usage": {"output_tokens": 1},
                                            "content": [
                                                {"type": "text", "text": CANARIES["prompt"]},
                                                {"type": "tool_use", "id": str(i), "name": "Bash",
                                                 "input": {"command": "echo " + CANARIES["secret"],
                                                           "cwd": CANARIES["path"]}}]}}))
        rows.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": str(i),
             "content": CANARIES["tool_result"] + " " + CANARIES["name"]}]}}))
    open(canary_path, "w", encoding="utf-8").write("\n".join(rows) + "\n")
    hist = os.path.join(d, "canary-history.jsonl")
    run = subprocess.run([sys.executable, os.path.join(TOOLS, "carry.py"), canary_path,
                          "--min-turns", "1", "--history", hist],
                         capture_output=True, text=True)
    sinks = {"history": open(hist, encoding="utf-8").read() if os.path.exists(hist) else "",
             "stdout": run.stdout, "stderr": run.stderr}
    leaks = []
    for sink, text in sinks.items():
        for kind, value in CANARIES.items():
            if value and value in text:
                leaks.append("%s in %s" % (kind, sink))
        if "secret-canary-dir" in text or leak_dir in text:
            leaks.append("path-fragment in %s" % sink)
    check("CANARY_LEAK=0 di setiap sink Phase 2", leaks, [])
    check("kontrol positif: akuisisi benar-benar membaca kanari itu",
          '"shares"' in sinks["history"] and "Bash" in sinks["history"], True)
    check("kontrol positif: kanari memang ada di sumbernya",
          CANARIES["secret"] in open(canary_path, encoding="utf-8").read(), True)
    check("history hanya memuat digest, bukan nama berkas",
          all(len(entry["path_digest"]) == 12 for entry in
              json.loads(sinks["history"].splitlines()[0])["payload"]["sample_manifest"]), True)

    # ---------------------------------------------------------------- OFFLINE
    banned = ("socket", "http", "http.client", "urllib", "requests", "httpx", "anthropic",
              "openai", "ssl")
    offenders = []
    paths = [os.path.join(TOOLS, p, n) for p in ("evidence", "wire")
             for n in sorted(os.listdir(os.path.join(TOOLS, p))) if n.endswith(".py")]
    paths += [os.path.join(TOOLS, n) for n in ("carry.py", "evidence_acquire.py",
                                               "evidence_history.py")]
    for path in paths:
        offenders += ["%s: %s" % (os.path.basename(path), name) for name in imports_of(path)
                      if name.split(".")[0] in banned]
    check("NETWORK_CALLS=0 / LLM_CALLS=0 di jalur bukti", offenders, [])

    # ---------------------------------------------------------------- SHADOW READINESS
    p = os.path.join(d, "shadow.jsonl")
    for i in range(6):
        carry.history(p, facts(20 + i, sources=2), 100, scope_id="s")
    container = evidence_history.read_container(p)
    scope, workload = make_scope_id("s"), make_workload_id("")
    population = population_for(container, scope, workload)
    state = history_integrity(container, Absence.KNOWN_ABSENT, scope, make_epoch(now))
    acquisition = AcquisitionIntegrity.worst(
        *[evaluate_observation(m, make_epoch(now)).effective for m in population.members])
    shadow = {}
    for name in sorted(FINDING_FLOORS):
        enough = sufficiency(make_finding_id(name),
                             make_sufficiency_facts(50, 500, 5000, True, 900, 60,
                                                    population.size, False))
        shadow[name] = {
            "container": state.integrity.value, "acquisition": acquisition.value,
            "sufficiency": enough.value,
            "gate": promotable(dependency_contract(name), acquisition, state.integrity, enough,
                               False, world_state(population.members, scope), True)}
    check("bayangan: kedua finding punya keadaan yang bisa dibaca", sorted(shadow),
          ["listing_cost", "write_guard_retirement"])
    check("bayangan: EVIDENCE_READY_FOR_FINDING", all(v["gate"] for v in shadow.values()), True)
    check("bayangan: populasi = yang benar-benar ada di file", population.size, 6)
    check("bayangan: nol artifact ditulis",
          [f for f in os.listdir(d) if f.endswith(".md")], [])
    # the shadow REPORTER: same four states, from the file, with no side effect at all
    import evidence_shadow
    before = sorted(os.listdir(d))
    rows, shadow_facts = evidence_shadow.shadow(p, "s", "", now)
    check("pelapor bayangan: dua finding", [r["finding"] for r in rows],
          ["listing_cost", "write_guard_retirement"])
    check("pelapor bayangan: populasi sama dengan kernel", shadow_facts["population"],
          population.size)
    check("pelapor bayangan: bukti live-sweep siap",
          [r["dependency_gate"] for r in rows if r["finding"] == "listing_cost"], [True])
    check("pelapor bayangan: finding ledger JUJUR belum siap (nol akuisisi ledger)",
          [r["sufficiency"] for r in rows if r["finding"] == "write_guard_retirement"],
          ["INSUFFICIENT"])
    check("pelapor bayangan: nol efek samping di direktori", sorted(os.listdir(d)), before)

    # --------------------------------------------------------------- REVIEW A: the six port defects
    # Every one of these was found by the bounded adversarial review of the port, reproduced here
    # first (RED), and fixed in the ADAPTERS — never in the frozen kernel.
    d = tempfile.mkdtemp()
    src = os.path.join(d, "unreadable.jsonl")
    transcript(src)
    os.chmod(src, 0)                                       # selected, and it cannot be read
    p = os.path.join(d, "failed.jsonl")
    run = subprocess.run([sys.executable, os.path.join(TOOLS, "carry.py"), src, "--history", p],
                         capture_output=True, text=True)
    c = evidence_history.read_container(p) if os.path.exists(p) else None
    check("sweep gagal menulis tombstone, bukan diam",
          [type(r).__name__ for r in (c.records if c else ())], ["CarrySweepFailed"])
    check("tombstone: tak ada carry dan tak ada manifest",
          (c.records[0].payload.carry_bytes, len(c.records[0].payload.sample_manifest)) if c
          else None, (0, 0))
    check("sweep gagal: exit code tetap menandai skema tak dikenal", run.returncode, 2)

    # Owner directive 17/31: the blank line stays COSMETIC. It is kept that way on purpose, and
    # the reason it costs nothing is below it: a record that disappears is caught by the CHAIN,
    # with or without a newline left in its place.
    d = tempfile.mkdtemp()
    p = os.path.join(d, "blank.jsonl")
    carry.history(p, facts(1), 100, scope_id="s")
    open(p, "a", encoding="utf-8").write("\n")
    c = evidence_history.read_container(p)
    check("baris kosong tetap kosmetik (arahan Owner 17/31)",
          (len(c.records), c.lines_rejected,
           history_integrity(c, Absence.KNOWN_ABSENT, make_scope_id("s"),
                             make_epoch(now)).integrity.value), (1, 0, "INTACT"))
    d = tempfile.mkdtemp()
    p = os.path.join(d, "hole.jsonl")
    for i in range(3):
        carry.history(p, facts(i + 1), 100, scope_id="s")
    rows = open(p, encoding="utf-8").read().splitlines()
    open(p, "w", encoding="utf-8").write(rows[0] + "\n" + "\n" + rows[2] + "\n")   # record 1 dihapus
    state = history_integrity(evidence_history.read_container(p), Absence.KNOWN_ABSENT,
                              make_scope_id("s"), make_epoch(now))
    check("record yang HILANG tertangkap rantai, bukan oleh menghitung baris kosong",
          (state.integrity.value, "chain_broken" in [r.value for r in state.reasons]),
          ("DEGRADED", True))

    # REVIEW B: a path that lost its identity before it could be frozen is a DISCOVERY loss —
    # calling it the outcome of a selected source breaks the accounting law and marks the whole
    # record UNVERIFIED for something that is really "discovery handed us a path that was gone".
    d = tempfile.mkdtemp()
    a = carry.accumulate([os.path.join(d, "vanished.jsonl")], 1)
    vanished = observe(a)
    ev = evidence_acquire.state_of(vanished, now)
    check("path yang lenyap sebelum identitasnya dibekukan = discovery loss",
          (a["counters"]["discovered"], a["counters"]["unreadable"],
           a["counters"]["dirs_unreadable"]), (0, 0, 1))
    check("akuntansi tetap sah: DEGRADED/discovery_incomplete, bukan UNVERIFIED",
          (ev.derived.value, [r.value for r in ev.reasons]), ("DEGRADED", ["discovery_incomplete"]))
    check("path yang lenyap: tetap tombstone, bukan pengukuran", type(vanished).__name__,
          "CarrySweepFailed")

    d = tempfile.mkdtemp()
    p = os.path.join(d, "tampered.jsonl")
    carry.history(p, facts(1), 100, scope_id="s")
    raw = open(p, "rb").read()
    key = b'"writer_version": "'
    i = raw.find(key) + len(key)
    open(p, "wb").write(raw[:i] + bytes([255]) + raw[i + 1:])
    c = evidence_history.read_container(p)
    check("byte non-UTF-8 dalam record tak pernah 'diperbaiki' jadi U+FFFD",
          (len(c.records), c.lines_rejected,
           history_integrity(c, Absence.KNOWN_ABSENT, make_scope_id("s"),
                             make_epoch(now)).integrity.value), (0, 1, "DEGRADED"))

    d = tempfile.mkdtemp()
    open(os.path.join(d, "empty.jsonl"), "w").close()      # terbaca, nol turn
    a = carry.accumulate([os.path.join(d, "empty.jsonl")], 1)
    check("sumber kosong punya outcome sendiri, bukan 'parsed'",
          (a["counters"]["empty_source"], len(a["parsed"])), (1, 0))
    check("sweep yang tak mengakuisisi apa pun = FAILED, bukan INTACT",
          evidence_acquire.state_of(observe(a), now).derived.value, "FAILED")

    d = tempfile.mkdtemp()
    p = os.path.join(d, "nolock.jsonl")
    real_flock = fcntl.flock
    fcntl.flock = lambda *a, **k: (_ for _ in ()).throw(OSError(errno.ENOLCK, "no locks"))
    try:
        written, note = evidence_history.append_chained(
            p, lambda seq, prev: evidence_acquire.encoded(observe(facts(1), seq=seq, prev=prev)),
            make_scope_id("s"))
    finally:
        fcntl.flock = real_flock
    check("tanpa lock: JANGAN menulis (posisi yang bertabrakan lebih buruk daripada gap)",
          (written, os.path.exists(p) and open(p).read()), (False, ""))

    d = tempfile.mkdtemp()
    p = os.path.join(d, "unsupported.jsonl")
    open(p, "w", encoding="utf-8").write(json.dumps(
        {"schema_version": 99, "record_type": "carry_run", "ts": 1, "turns": 10,
         "scope_id": "s", "shares": {"Bash": 100.0}}) + "\n")
    check("generasi di luar PRODUCTION_LEGACY_SCHEMAS tak pernah jadi pembanding delta",
          evidence_history.read_views(p), [])
    check("generasi di luar allowlist = baris ditolak, bukan legacy",
          (evidence_history.read_container(p).lines_rejected,
           len(evidence_history.read_container(p).legacy)), (1, 0))

    d = tempfile.mkdtemp()
    p = os.path.join(d, "zero.jsonl")
    zero = facts(1, carry_map={"Bash": 0})                 # semua isi jatuh di turn terakhir
    zero["carry_total"] = 0
    check("carry nol: share kosong, bukan share nol yang jadi conservation violation",
          evidence_acquire.state_of(observe(zero), now).derived.value, "INTACT")

    print("\n%d PASS / %d FAIL" % (P, F))
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
