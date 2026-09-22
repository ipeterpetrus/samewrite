#!/usr/bin/env python3
"""Issue #15 — candidate path containment. One oracle per row of docs/V142_COUNTEREXAMPLES.md §8.

A candidate_id is a LOGICAL identity that carries the analysed scope verbatim. It used to be the
directory name as well, so a scope such as `x/../../up` put HYPOTHESIS.md outside the operator's
--emit-candidate root, a NUL in a scope ended in a traceback, and a symlink already sitting at the
candidate's directory name was followed out of the root.

Every case runs the real CLI inside a fresh sandbox whose emit root sits twelve directories deep:
even a broken implementation cannot climb out of the sandbox, and every file is found by walking
the sandbox and resolving it, never by reading the identifier.

The last section proves the oracles bite: each named mutant is applied to a throwaway copy of
tools/ and the oracle guarding it must go RED there while staying GREEN on the real source.

Standalone: run this file. `--tools DIR --oracle NAME` runs one oracle against another tools/."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
DEPTH = 12
TS0 = 1_750_000_000
HASHED = "candidate-sha256-"
P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: got {got!r}, want {want!r}")


def expected_storage(cid):
    """The frozen storage rule, written out again here: an oracle that imported the helper it
    checks would agree with any mutant of it."""
    if cid in ("", ".", "..") or cid.upper().startswith(HASHED.upper()) or "/" in cid or "\\" in cid:
        return HASHED + hashlib.sha256(cid.encode("utf-8", "surrogatepass")).hexdigest()
    return cid


def rec(i, scope):
    b = 20.0 + i * 5
    return {"schema_version": 2, "record_type": "carry_run", "run_id": f"r{i}",
            "ts": TS0 + i * 604800, "sessions": 60, "turns": 3000, "carry_bytes": 10 ** 8,
            "scanned": 120, "unreadable": 0, "oversize": 0, "skipped_by_limit": 0,
            "scope_id": scope, "workload_class": "", "evidence_quality": "COMPLETE",
            "runtimes": {"2.1.271": 60}, "models": {"m": 60},
            "shares": {"Bash": b, "Read": 100.0 - b}, "bpt": {"Bash": 1.0, "Read": 1.0}}


class Sandbox:
    def __init__(self, base):
        self.dir = tempfile.mkdtemp(prefix="sb-", dir=base)
        self.emit = os.path.join(self.dir, "root", *[f"lvl{k}" for k in range(1, DEPTH)], "emit")
        self.outside = os.path.join(self.dir, "outside_target")
        os.makedirs(self.emit)
        os.makedirs(self.outside)

    def run(self, tools, scope=None, hist_scope=None, json_out=True):
        """-> (rc, parsed json or None, stdout, stderr). A --scope-id case is carried by a ledger
        finding, so no history is needed; a history case is carried by a six-record trend."""
        h, led = os.path.join(self.dir, "history.jsonl"), os.path.join(self.dir, "ledger.jsonl")
        with open(h, "w", encoding="utf-8") as fh:
            for i in range(6 if hist_scope is not None else 0):
                fh.write(json.dumps(rec(i, hist_scope)) + "\n")
        with open(led, "w", encoding="utf-8") as fh:
            fh.write('{"event": "checked"}\n' * (120 if scope is not None else 0))
        cmd = [sys.executable, os.path.join(tools, "optimize.py"), "--history", h, "--ledger", led,
               "--scan", "--strict-exit", "--emit-candidate", self.emit]
        cmd += ["--json"] if json_out else []
        cmd += ["--scope-id", scope] if scope is not None else []
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=self.dir,
                           env=dict(os.environ, HOME=self.dir))
        try:
            j = json.loads(p.stdout) if json_out else None
        except ValueError:
            j = None
        return p.returncode, j, p.stdout, p.stderr

    def census(self):
        """Every artefact in the sandbox, resolved: (HYPOTHESIS.md paths, temp files, locks)."""
        root = os.path.realpath(self.emit)
        hyp, tmp, lock = [], [], []
        for r, _ds, fs in os.walk(self.dir, followlinks=True):
            for f in fs:
                real = os.path.realpath(os.path.join(r, f))
                if f == "HYPOTHESIS.md":
                    hyp.append((os.path.relpath(real, root), os.path.commonpath([root, real]) == root))
                elif ".tmp-" in f:
                    tmp.append(f)
                elif f == ".optimize.lock":
                    lock.append(f)
        return sorted(set(hyp)), sorted(set(tmp)), lock


# ---------------------------------------------------------------- oracles: (tools, tmp) -> [(label, got, want)]
def clean_run(label, sb, rc, j, err):
    _hyp, tmp, lock = sb.census()
    return [(f"{label}: machine-readable result, no traceback", (j is not None, "Traceback" in err), (True, False)),
            (f"{label}: no temporary file, no lock left", (tmp, lock), ([], []))]


def o_safe(tools, base):
    """PATH_01/02/07: an id that is already one ordinary component is its own directory name."""
    out = []
    for case, scope in (("PATH_01", "default"), ("PATH_02", "agent-a"), ("PATH_07", ".."), ("PATH_07", ".")):
        sb = Sandbox(base)
        rc, j, _o, err = sb.run(tools, hist_scope=scope)
        out += clean_run(f"{case} {scope!r}", sb, rc, j, err)
        if not j:
            continue
        cid = j["candidate_ids"][0] if j["candidate_ids"] else None
        out.append((f"{case} {scope!r}: written under its own logical id",
                    (j["status"], rc, j["candidates_written"], sb.census()[0]),
                    ("CANDIDATE", 10, [cid], [(os.path.join(str(cid), "HYPOTHESIS.md"), True)])))
    return out


UNSAFE = (("PATH_03", "cli", "x/../../up"), ("PATH_04", "cli", "x/../../../../up4"),
          ("PATH_05", "cli", "a/b/c/" + "../" * 12 + "deep"), ("PATH_06", "hist", "team/a"),
          ("PATH_06", "hist", "a\\..\\..\\b"), ("PATH_07", "hist", "a/./b"),
          ("PATH_08", "hist", "/abs/x"), ("PATH_09", "hist", "x/../../../hist"),
          ("PATH_10", "cli", "x/../../../cli"))


def o_contained(tools, base):
    """PATH_03..10: a separator-bearing id is stored under its digest, inside the root, and the
    specification still names the LOGICAL identity."""
    out = []
    for case, surface, scope in UNSAFE:
        sb = Sandbox(base)
        rc, j, _o, err = sb.run(tools, **({"scope": scope} if surface == "cli" else {"hist_scope": scope}))
        label = f"{case} {surface} {scope!r}"
        out += clean_run(label, sb, rc, j, err)
        if not j:
            continue
        cid = j["candidate_ids"][0] if j["candidate_ids"] else ""
        hyp = sb.census()[0]
        out.append((f"{label}: CANDIDATE, written under the logical id",
                    (j["status"], rc, j["candidates_written"]), ("CANDIDATE", 10, [cid])))
        out.append((f"{label}: exactly one file, inside the root, in the digest directory",
                    hyp, [(os.path.join(expected_storage(cid), "HYPOTHESIS.md"), True)]))
        spec = os.path.join(sb.emit, expected_storage(cid), "HYPOTHESIS.md")
        text = open(spec, encoding="utf-8").read() if os.path.isfile(spec) else ""
        out.append((f"{label}: the specification names the logical candidate_id and scope_id",
                    (f"candidate_id: {cid}\n" in text, f"scope_id: {scope}\n" in text), (True, True)))
    return out


def o_nul(tools, base):
    """PATH_11: a NUL in the scope is refused through the machine-readable path."""
    sb = Sandbox(base)
    rc, j, _o, err = sb.run(tools, hist_scope="a\x00b")
    out = clean_run("PATH_11 NUL", sb, rc, j, err)
    if j:
        out.append(("PATH_11 NUL: INTERNAL_ERROR 50, the logical id reported as failed",
                    (j["status"], rc, j["candidates_written"], j["candidates_failed"] == j["candidate_ids"],
                     len(j["candidate_ids"])), ("INTERNAL_ERROR", 50, [], True, 1)))
    out.append(("PATH_11 NUL: no specification anywhere", sb.census()[0], []))
    sb2 = Sandbox(base)
    rc2, _j, text, err2 = sb2.run(tools, hist_scope="a\x00b", json_out=False)
    line = [ln for ln in text.splitlines() if "could NOT be written" in ln]
    out.append(("PATH_11 NUL, human report: one refusal line, static reason, exit 50, no traceback",
                (len(line), bool(line) and line[0].endswith("not a single directory inside the output root"),
                 rc2, "Traceback" in err2), (1, True, 50, False)))
    return out


def o_dedup(tools, base):
    """PATH_12: the same unsafe logical candidate twice is one directory, written once."""
    sb = Sandbox(base)
    _rc1, j1, _o, _e1 = sb.run(tools, hist_scope="x/../../../rep")
    cid = j1["candidate_ids"][0] if j1 and j1["candidate_ids"] else ""
    spec = os.path.join(sb.emit, expected_storage(cid), "HYPOTHESIS.md")
    before = (open(spec, "rb").read(), os.stat(spec).st_mtime_ns) if os.path.isfile(spec) else None
    rc2, j2, _o, err2 = sb.run(tools, hist_scope="x/../../../rep")
    after = (open(spec, "rb").read(), os.stat(spec).st_mtime_ns) if os.path.isfile(spec) else None
    out = clean_run("PATH_12 second run", sb, rc2, j2, err2)
    if j1 and j2:
        out.append(("PATH_12: first written, second EXISTING, same logical id",
                    (j1["candidates_written"], j2["candidates_written"], j2["candidates_existing"]),
                    ([cid], [], [cid])))
    out.append(("PATH_12: one directory in the root, file not rewritten",
                (sorted(os.listdir(sb.emit)), before is not None and before == after),
                ([expected_storage(cid)], True)))
    return out


def o_distinct(tools, base):
    """PATH_13: two different unsafe logical candidates never share a directory."""
    sb = Sandbox(base)
    ids = []
    for scope in ("x/../../A", "x/../../B"):
        _rc, j, _o, _e = sb.run(tools, scope=scope)
        ids += (j or {}).get("candidates_written", [])
    want = sorted({expected_storage(c) for c in ids})
    return [("PATH_13: two logical ids, two written, two different directories, both inside",
             (len(ids), sorted(os.listdir(sb.emit)), [ok for _p, ok in sb.census()[0]]),
             (2, want if len(want) == 2 else ["<collision>"], [True, True]))]


def o_preexisting(tools, base):
    """PATH_14: a storage directory that already holds the specification is EXISTING, untouched."""
    out = []
    for kind, scope in (("safe", "agent-p"), ("unsafe", "x/../../pre")):
        cid = Sandbox(base).run(tools, scope=scope)[1]["candidate_ids"][0]
        sb = Sandbox(base)
        d = os.path.join(sb.emit, expected_storage(cid))
        os.makedirs(d)
        with open(os.path.join(d, "HYPOTHESIS.md"), "w") as fh:
            fh.write("PREEXISTING\n")
        rc, j, _o, err = sb.run(tools, scope=scope)
        out += clean_run(f"PATH_14 {kind}", sb, rc, j, err)
        out.append((f"PATH_14 {kind}: EXISTING, not written, content untouched",
                    ((j or {}).get("candidates_existing"), (j or {}).get("candidates_written"),
                     open(os.path.join(d, "HYPOTHESIS.md")).read()), ([cid], [], "PREEXISTING\n")))
    return out


def o_writefail(tools, base):
    """PATH_15: a regular file where the directory goes fails cleanly, inside a valid root."""
    out = []
    for kind, scope in (("safe", "agent-f"), ("unsafe", "x/../../fail")):
        cid = Sandbox(base).run(tools, scope=scope)[1]["candidate_ids"][0]
        sb = Sandbox(base)
        blocker = os.path.join(sb.emit, expected_storage(cid))
        with open(blocker, "w") as fh:
            fh.write("x")
        rc, j, _o, err = sb.run(tools, scope=scope)
        out += clean_run(f"PATH_15 {kind}", sb, rc, j, err)
        out.append((f"PATH_15 {kind}: INTERNAL_ERROR 50, failed, nothing written anywhere",
                    ((j or {}).get("status"), rc, (j or {}).get("candidates_failed"), sb.census()[0],
                     open(blocker).read()), ("INTERNAL_ERROR", 50, [cid], [], "x")))
    return out


def o_symlink(tools, base):
    """PATH_16: a symlink planted at the storage name is refused, not followed out of the root."""
    cid = Sandbox(base).run(tools, scope="agent-s")[1]["candidate_ids"][0]
    sb = Sandbox(base)
    link = os.path.join(sb.emit, expected_storage(cid))
    os.symlink(sb.outside, link)
    rc, j, _o, err = sb.run(tools, scope="agent-s")
    return clean_run("PATH_16", sb, rc, j, err) + [
        ("PATH_16: INTERNAL_ERROR 50, failed, the outside sibling stays empty, the link untouched",
         ((j or {}).get("status"), rc, (j or {}).get("candidates_failed"), os.listdir(sb.outside),
          os.path.islink(link)), ("INTERNAL_ERROR", 50, [cid], [], True))]


def _import(tools):
    for m in ("optimize", "carry", "skills", "profiles", "msgid"):
        sys.modules.pop(m, None)
    sys.path.insert(0, tools)
    try:
        import optimize
    finally:
        sys.path.remove(tools)
    return optimize


def o_guard(tools, base):
    """The emitter's own guard: a caller whose storage mapping is the identity must be refused."""
    optimize = _import(tools)
    sb = Sandbox(base)
    f = optimize.finding("guard", "CANDIDATE", "h", "e", scope="x/../../../guard")
    saved = getattr(optimize, "candidate_storage_component", None)
    optimize.candidate_storage_component = lambda c: c
    try:
        w, _e, fail = optimize.emit_candidates([f], sb.emit, "CANDIDATE")
    except Exception as exc:                        # noqa: BLE001 — the oracle reports, never crashes
        w, fail = ["raised " + type(exc).__name__], []
    finally:
        if saved is not None:
            optimize.candidate_storage_component = saved
    return [("GUARD: an unmapped traversal id handed straight to the emitter is refused, nothing lands",
             (w, [c for c, _why in fail], sb.census()[0]), ([], [f["candidate_id"]], []))]


def o_helper(tools, base):
    """The mapping itself: stable for ordinary ids, one safe distinct component for the rest."""
    optimize = _import(tools)
    h = getattr(optimize, "candidate_storage_component", None)
    if h is None:
        return [("HELPER: candidate_storage_component exists", False, True)]
    safe = ["trend-bash-default-c806aa12", "noop-guard-retire-agent-a-1234abcd", "trend-bash-..-73f155b7",
            "listing-prune-team-a-0000ffff", "a\x7fb", "x" * 200]
    unsafe = ["a/b", "a\\b", "..", ".", "", "/abs", "x/../../up", HASHED + "0" * 64, HASHED + "x",
              HASHED.upper() + "AB", "Candidate-Sha256-x", "candidate-\u017fha256-x", "cand\u0131date-sha256-x"]
    out = [("HELPER: ordinary ids are their own directory name, byte for byte",
            [h(c) for c in safe], safe)]
    names = [h(c) for c in unsafe]
    out.append(("HELPER: every other id is the digest of the complete logical id",
                names, [expected_storage(c) for c in unsafe]))
    out.append(("HELPER: never a separator, a dot segment or a NUL",
                [n for n in names if "/" in n or "\\" in n or n in (".", "..", "") or "\x00" in n], []))
    many = ["s/%d" % i for i in range(2000)]
    out.append(("HELPER: two thousand different unsafe ids, as many directories, stable on repeat",
                (len({h(c) for c in many}), [h(c) for c in many] == [h(c) for c in many]), (2000, True)))
    out.append(("HELPER: NUL, unencodable text and a non-string are refused, not hashed",
                [h("a\x00b"), h("\x00"), h("a\ud800b"), h(12345)], [None, None, None, None]))
    # A case-insensitive volume (macOS, Windows) is one directory for names equal under folding,
    # so a verbatim id must never fold onto a hashed name. The upper-cased hashed name of `a/b` is
    # the concrete collision the cross-family review of the first cut found.
    # NTFS compares UPPER-cased names, macOS folds case: both models are checked, and the probes
    # include the two letters that reach ASCII only through them (U+0131 dotless i, U+017F long s).
    hashed = [expected_storage(u) for u in unsafe]
    probe = (safe + unsafe + [n.upper() for n in hashed] + [c.upper() for c in safe]
             + [n.replace("i", "\u0131", 1) for n in hashed] + [n.replace("s", "\u017f", 1) for n in hashed])
    for model, fold in (("upper-casing (NTFS)", str.upper), ("case folding (macOS)", str.casefold)):
        stored = {}
        for c in probe:
            stored.setdefault(fold(h(c)), set()).add(c)
        out.append((f"HELPER: under {model}, ids that differ beyond letter case never share a directory",
                    sorted(sorted(v) for v in stored.values() if len({fold(x) for x in v}) > 1), []))
    return out


_AUDIT = {"sink": None}
# event -> positions of its PATH arguments (the rest are modes, flags and descriptors)
_FS_EVENTS = {"open": (0,), "os.mkdir": (0,), "os.rename": (0, 1), "os.remove": (0,), "os.rmdir": (0,),
              "os.symlink": (0, 1), "os.link": (0, 1), "os.chmod": (0,), "os.utime": (0,),
              "os.listdir": (0,), "os.scandir": (0,), "os.truncate": (0,), "os.chown": (0,), "os.chdir": (0,)}


def _audit(event, args):
    sink = _AUDIT["sink"]
    if sink is not None and event in _FS_EVENTS:
        sink.extend(os.fsdecode(args[i]) for i in _FS_EVENTS[event]
                    if i < len(args) and isinstance(args[i], (str, bytes)))


sys.addaudithook(_audit)


def o_inspect(tools, base):
    """Not only does no file land outside the root: no filesystem call made for a candidate even
    LOOKS outside it. Every path handed to os/os.path/open while the emitter runs is recorded, and
    each must be the root, inside it, or one of its ancestors (resolving the root itself)."""
    import builtins
    optimize = _import(tools)
    sb = Sandbox(base)
    root = os.path.realpath(sb.emit)
    seen = []

    def spy(fn):
        def wrapped(*a, **k):
            if a and isinstance(a[0], (str, bytes, os.PathLike)):
                seen.append(os.fsdecode(a[0]))
            return fn(*a, **k)
        return wrapped

    # Two nets, because neither is complete alone: wrappers catch the INSPECTING calls (stat, access,
    # readlink — CPython raises no audit event for them), and an audit hook catches every open,
    # create, rename, remove and listing, including ones made through pathlib or io directly.
    targets = ([(os.path, n) for n in ("exists", "lexists", "isdir", "isfile", "islink", "samefile",
                                        "realpath", "getsize", "getmtime")]
               + [(os, n) for n in ("stat", "lstat", "access", "readlink", "makedirs", "mkdir", "replace",
                                    "rename", "unlink", "remove", "rmdir", "open", "listdir", "scandir",
                                    "chmod", "utime", "link", "symlink")] + [(builtins, "open")])
    fs = [optimize.finding("inspect", "CANDIDATE", "h", "e", scope=sc) for sc in ("x/../../up", "/abs/x", "a\x00b", "ok")]
    saved = [(m, n, getattr(m, n)) for m, n in targets if hasattr(m, n)]
    for m, n, fn in saved:
        setattr(m, n, spy(fn))
    _AUDIT["sink"] = seen                           # the emitter's calls only, not finding()'s
    try:
        w, _e, fail = optimize.emit_candidates(fs, sb.emit, "CANDIDATE")
    except Exception as exc:                        # noqa: BLE001 — the oracle reports, never crashes
        w, fail = ["raised " + type(exc).__name__], []
    finally:
        _AUDIT["sink"] = None
        for m, n, fn in saved:
            setattr(m, n, fn)

    def outside(p):
        a = os.path.normpath(os.path.abspath(p))
        common = os.path.commonpath([root, a])
        return common != root and common != a
    return [("INSPECT: three written, the NUL id failed",
             (sorted(w), [c for c, _why in fail]),
             (sorted(f["candidate_id"] for f in fs if "\x00" not in f["candidate_id"]), [fs[2]["candidate_id"]])),
            ("INSPECT: the spy saw the files it wrote (it is not vacuous)",
             sum(1 for p in seen if p.endswith("HYPOTHESIS.md") and not outside(p)) >= 3, True),
            ("INSPECT: no path outside the root was stat-ed, opened, created or replaced",
             sorted({p for p in seen if outside(p)}), [])]


ORACLES = {"safe": o_safe, "contained": o_contained, "nul": o_nul, "dedup": o_dedup,
           "distinct": o_distinct, "preexisting": o_preexisting, "writefail": o_writefail,
           "symlink": o_symlink, "guard": o_guard, "helper": o_helper, "inspect": o_inspect}


# ---------------------------------------------------------------- the oracles must bite
MUTANTS = [
    ("M_RAW_CANDIDATE_ID_USED_AS_PATH", ["contained"],
     '        d = candidate_dir(root, f["candidate_id"])\n',
     '        d = os.path.join(outdir, f["candidate_id"])\n'),
    ("M_TRAVERSAL_STORAGE_NOT_MAPPED", ["contained"],
     '            or "/" in candidate_id or "\\\\" in candidate_id):\n', '            ):\n'),
    ("M_NUL_UNCAUGHT", ["nul"],
     '    if not isinstance(candidate_id, str) or "\\x00" in candidate_id:\n',
     '    if not isinstance(candidate_id, str):\n'),
    ("M_CONTAINMENT_GUARD_REMOVED", ["guard"],
     '    if os.path.dirname(d) != root:\n', '    if False:\n'),
    ("M_UNSAFE_STORAGE_COLLISION", ["distinct", "helper"],
     'candidate_id.encode("utf-8", "surrogatepass")).hexdigest()', 'b"").hexdigest()'),
    ("M_SAFE_ID_PATH_CHANGED", ["safe", "helper"],
     '    return candidate_id\n\n\ndef candidate_dir',
     '    return STORAGE_HASHED_PREFIX + hashlib.sha256(candidate_id.encode()).hexdigest()\n\n\n'
     'def candidate_dir'),
    ("M_EXISTING_UNSAFE_CANDIDATE_NOT_DEDUPED", ["dedup"],
     'candidate_id.encode("utf-8", "surrogatepass")).hexdigest()',
     '(candidate_id + str(os.getpid())).encode("utf-8", "surrogatepass")).hexdigest()'),
    ("M_PREEXISTING_SYMLINK_FOLLOWED", ["symlink"],
     '    if os.path.islink(d):\n', '    if False:\n'),
    ("M_RESERVED_PREFIX_CASE_SENSITIVE", ["helper"],
     'candidate_id.upper().startswith(STORAGE_HASHED_PREFIX.upper())',
     'candidate_id.startswith(STORAGE_HASHED_PREFIX)'),
    ("M_RESERVED_PREFIX_CASEFOLD_MODEL_ONLY", ["helper"],
     'candidate_id.upper().startswith(STORAGE_HASHED_PREFIX.upper())',
     'candidate_id.casefold().startswith(STORAGE_HASHED_PREFIX)'),
    ("M_INSPECT_RAW_PATH_BEFORE_GUARD", ["inspect"],
     '        d = candidate_dir(root, f["candidate_id"])\n',
     '        os.path.lexists(os.path.join(outdir, f["candidate_id"], "HYPOTHESIS.md"))\n'
     '        d = candidate_dir(root, f["candidate_id"])\n'),
    ("M_INSPECT_RAW_PATH_VIA_ACCESS", ["inspect"],
     '        d = candidate_dir(root, f["candidate_id"])\n',
     '        try:\n'
     '            os.access(os.path.join(outdir, f["candidate_id"], "HYPOTHESIS.md"), os.F_OK)\n'
     '        except (OSError, ValueError):\n'
     '            pass\n'
     '        d = candidate_dir(root, f["candidate_id"])\n'),
    ("M_WRITE_RAW_PATH_VIA_PATHLIB", ["inspect"],
     '        d = candidate_dir(root, f["candidate_id"])\n',
     '        try:\n'
     '            __import__("pathlib").Path(outdir, f["candidate_id"] + ".probe").open("a").close()\n'
     '        except (OSError, ValueError):\n'
     '            pass\n'
     '        d = candidate_dir(root, f["candidate_id"])\n'),
]


def oracle_holds(tools, names, base):
    """Run named oracles against a tools/ copy in a fresh interpreter -> (all held, failing lines)."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--tools", tools,
                        "--oracle", ",".join(names), "--tmp", base],
                       capture_output=True, text=True, timeout=600)
    bad = [ln.strip()[len("FAIL"):].strip() for ln in p.stdout.splitlines() if ln.startswith("  FAIL")]
    return p.returncode == 0 and not bad, bad or [p.stderr.strip()[-200:]]


def main():
    args = sys.argv[1:]
    if "--oracle" in args:
        tools = args[args.index("--tools") + 1]
        names = args[args.index("--oracle") + 1].split(",")
        base = args[args.index("--tmp") + 1]
        for n in names:
            for label, got, want in ORACLES[n](tools, base):
                check(label, got, want)
        sys.exit(1 if F else 0)

    base = tempfile.mkdtemp(prefix="sw-cpath-")
    try:
        for name, fn in ORACLES.items():
            print(f"\n--- {name}")
            for label, got, want in fn(TOOLS, base):
                check(label, got, want)

        print("\n--- mutants: each must turn its oracle RED on a copy of tools/")
        src = open(os.path.join(TOOLS, "optimize.py"), encoding="utf-8").read()
        for mname, names, old, new in MUTANTS:
            if src.count(old) != 1:
                check(f"{mname}: the mutated line exists exactly once", src.count(old), 1)
                continue
            copy = os.path.join(base, "tools-" + mname)
            shutil.copytree(TOOLS, copy, ignore=shutil.ignore_patterns("__pycache__"))
            with open(os.path.join(copy, "optimize.py"), "w", encoding="utf-8") as fh:
                fh.write(src.replace(old, new))
            held, bad = oracle_holds(copy, names, base)
            check(f"{mname}: oracle {'+'.join(names)} goes RED", held, False)
            if not held and bad:
                print(f"        first red: {bad[0][:160]}")
        # the same oracles across the same process boundary on the real source: a RED here would
        # mean the oracle, not the implementation, is what the mutants were failing
        names = sorted({n for _m, ns, _o, _n in MUTANTS for n in ns})
        held, bad = oracle_holds(TOOLS, names, base)
        check("control: the same oracles are GREEN on the real tools/", (held, [] if held else bad[:1]), (True, []))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print(f"\n{P} PASS / {F} FAIL")
    sys.exit(1 if F else 0)


if __name__ == "__main__":
    main()
