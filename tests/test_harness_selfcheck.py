#!/usr/bin/env python3
"""The evidence-quality harness must be able to fail.

The acceptance review that found SW-1303 also found a false green in the instrument that found it:
a harness that recorded a known invariant violation and still closed "28 PASS / 0 FAIL". A suite
whose only demonstrated behaviour is passing proves nothing about the code it points at.

So this file attacks tests/test_evidence_quality.py the way test_mutation.py attacks tools/: it
plants three specific corruptions in a throwaway copy and requires the copy to FAIL. It also
asserts the harness still carries live positive controls, because a fail-closed fix that blocks
everything would otherwise pass a matrix made only of blocked cases.

Standalone: run this file."""
import os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(ROOT, "tests", "test_evidence_quality.py")
PY = sys.executable
P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: got {got!r}, want {want!r}")


def run_copy(mutations):
    """Copy the harness, apply mutations, run it. -> (exit code, tail of output)."""
    d = tempfile.mkdtemp(prefix="sw-hsc-")
    try:
        dst_tests = os.path.join(d, "tests")
        os.makedirs(dst_tests)
        # the harness resolves ROOT from its own location, so mirror the tree it expects
        os.symlink(os.path.join(ROOT, "tools"), os.path.join(d, "tools"))
        src = open(HARNESS, encoding="utf-8").read()
        for old, new in mutations:
            assert src.count(old) == 1, f"plant pattern not unique: {old[:60]!r}"
            src = src.replace(old, new)
        q = os.path.join(dst_tests, "h.py")
        open(q, "w", encoding="utf-8").write(src)
        r = subprocess.run([PY, q], capture_output=True, text=True, timeout=1800)
        return r.returncode, (r.stdout + r.stderr)[-600:]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    src = open(HARNESS, encoding="utf-8").read()

    # ---------------------------------------------------------------- it passes unmutated
    rc, tail = run_copy([])
    check("CONTROL: an unmutated copy of the harness passes", rc, 0)
    if rc != 0:
        print("    " + tail.replace("\n", "\n    "))
        print(f"\n{P} PASS / {F} FAIL")
        return 1

    # ---------------------------------------------------------------- 1. a known-bad expectation
    # Restore the defect's behaviour as the EXPECTED outcome. A harness that cannot tell the fixed
    # code from the broken code would still pass.
    rc1, _ = run_copy([('("B", "PARTIAL history only, no acceptance",\n'
                        '     dict(records=moving(quality="PARTIAL")), "PARTIAL_EVIDENCE", 0),',
                        '("B", "PARTIAL history only, no acceptance",\n'
                        '     dict(records=moving(quality="PARTIAL")), "CANDIDATE", 1),')])
    check("a known-bad expectation makes the harness fail", rc1 != 0, True)

    # ---------------------------------------------------------------- 2. a dead positive control
    # If the accepted-PARTIAL path silently stopped producing candidates, the matrix must notice.
    rc2, _ = run_copy([('("M", "accepted PARTIAL bounded evidence still produces a candidate",\n'
                        '     dict(records=moving(quality="PARTIAL"), accept_partial=True), "CANDIDATE", 1),',
                        '("M", "accepted PARTIAL bounded evidence still produces a candidate",\n'
                        '     dict(records=moving(quality="PARTIAL"), accept_partial=True), "PARTIAL_EVIDENCE", 0),')])
    check("a dead positive control makes the harness fail", rc2 != 0, True)

    # ---------------------------------------------------------------- 3. zero parsed history
    # The fixture writer emits nothing. Every case collapses to "no evidence" and a harness with no
    # control over its own inputs would report a clean sweep of blocked cases.
    rc3, _ = run_copy([("        for r in records:\n            fh.write(json.dumps(r) + \"\\n\")",
                        "        for r in []:\n            fh.write(json.dumps(r) + \"\\n\")")])
    check("a history fixture that writes nothing makes the harness fail", rc3 != 0, True)

    # ---------------------------------------------------------------- 4. the controls must exist
    # A fail-closed change could be "passed" by a matrix containing only blocked cases. Require
    # that the matrix still asserts real candidate production, in both the complete and the
    # explicitly-accepted-partial direction.
    # Read the MATRIX object, not the file's text. A regex over nested dict(...) literals was the
    # first attempt and it found one case out of five — a detector that under-reports is exactly
    # the kind of instrument this file exists to reject.
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("sw_eq_harness", HARNESS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cases_with_candidates = sorted({case for case, _d, _k, status, files in mod.MATRIX
                                    if status == "CANDIDATE" and files >= 1})
    check("the matrix still contains at least two live positive controls",
          len(cases_with_candidates) >= 2, True)
    print(f"        positive controls present: {cases_with_candidates}")
    check("one of them is the accepted-PARTIAL path (so the flag is not dead functionality)",
          "M" in cases_with_candidates, True)
    check("one of them is the plain COMPLETE path", "A" in cases_with_candidates, True)

    # ---------------------------------------------------------------- 5. no silent skipping
    check("the harness fails the process when any check fails",
          "return 1 if F else 0" in src, True)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
