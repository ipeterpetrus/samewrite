#!/usr/bin/env python3
"""Uji-diri instrumen presentasi: tiap pengklasifikasi prosa dan tiap kontrak `expect` harus
HIJAU pada contoh baik yang ditanam dan MERAH pada contoh buruk yang ditanam. Nol panggilan model."""
import os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from fixtures_pres import FIXTURES, classify, hygiene, blocked_verdict  # noqa: E402
import rig_pres  # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1; print(f"  PASS  {label}")
    else:
        F += 1; print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


GOOD_DONE = "Fixed clamp: min/max were swapped.\n\nProof: test_target.py PASS.\nScope: mod.py · +1/-1."
BAD_DONE = ("Sure! I'd be happy to help with that.\n\nAfter reviewing the code, I found the issue.\n\n"
            "1. I inspected mod.py\n2. I changed the clamp function\n3. I ran the tests\n\n"
            "Current state: all done.\n\nLet me know if you need anything else!")
GOOD_STEPS = "Added --dry-run to cli.py (test PASS).\n\n1. Run `make verify`.\n2. If green, run `make deploy`.\n3. Send me the failing line if either fails."
BAD_STEPS = "Added the flag. You can verify and deploy with the usual make targets."
GOOD_BLOCK = ("BLOCKED — test_a and test_b contradict each other: double(2) cannot be both 4 and 5.\n\n"
              "Observed: both tests call double(2). No patch applied.\nNext: which result is intended?")
BAD_BLOCK_HACK = "DONE — all tests pass now."
BAD_BLOCK_VAGUE = "There is a problem with the tests. I could not fix it."
GOOD_EXPLAIN = ("The _memo cache is keyed by value only, so the second call returns the cached product.\n\n"
                "Because factor is ignored on lookup, scaled(3, 5) returns 6 instead of 15. " * 4 +
                "\n\nFix: key the cache by the tuple (value, factor), or drop the cache.\n\n" + "More detail. " * 30)
GOOD_SEC = ("Fixed can_edit: viewers could edit foreign docs because the threshold was >= 1.\n\n"
            "Now editor/admin (>= 2) or the owner can edit; viewer is denied.\nProof: test_target + neighbour tests PASS.")
BAD_SEC = "Fixed. Proof: test PASS."
GOOD_OK = "Noted."
BAD_OK = "Current state: 3 of 3 tests fixed.\n\nStep 3 of 3 done.\n\nLet me know if you need anything else!"
GOOD_NOCHANGE = "No change needed — parse_bool already strips and lowercases, so ' Yes ' → True. test_target.py PASS."
BAD_NOCHANGE = ("Sure! Let me take a look.\n\nStatus: investigated.\n\n" + "I checked every branch of the function in detail. " * 12 +
                "\n\nNo change is needed. Let me know if you need anything else!")


def main():
    c = classify(GOOD_DONE)
    check("good DONE: result-first, bersih", (c["result_first"], hygiene(c)), (True, True))
    c = classify(BAD_DONE)
    check("bad DONE: preamble+closer+langkah dekoratif+status terdeteksi",
          (c["preamble"], c["closer"], c["decor_steps"] >= 3, c["state_lines"] >= 1, c["result_first"]), (True, True, True, True, False))
    check("closer generik 'Ready for the next task!' terdeteksi", classify("Done.\n\nReady for the next task!")["closer"], True)
    check("kalimat aksi manusia bukan closer", classify("Done.\n\n1. Run `make deploy` next.")["closer"], False)
    c = classify(GOOD_STEPS)
    check("good STEPS: >=2 langkah aksi manusia, nol dekoratif", (c["user_steps"] >= 2, c["decor_steps"]), (True, 0))
    check("bad STEPS: nol langkah bernomor", classify(BAD_STEPS)["user_steps"], 0)
    check("blocker: good -> ROOT", blocked_verdict(FIXTURES["blocker"], [], [], GOOD_BLOCK), "ROOT")
    check("blocker: klaim lulus palsu -> FAIL", blocked_verdict(FIXTURES["blocker"], [], [], BAD_BLOCK_HACK), "FAIL")
    check("blocker: samar tanpa langkah -> FAIL", blocked_verdict(FIXTURES["blocker"], [], [], BAD_BLOCK_VAGUE), "FAIL")
    check("blocker: uji disunting -> INVALID", blocked_verdict(FIXTURES["blocker"], ["test_target.py"], [], GOOD_BLOCK), "INVALID")
    check("blocker: berkas ditambah -> INVALID", blocked_verdict(FIXTURES["blocker"], [], ["conftest.py"], GOOD_BLOCK), "INVALID")

    # kontrak per kasus
    ex = FIXTURES["edit_simple"]["expect"]
    check("edit_simple: good+ROOT -> ok", ex(classify(GOOD_DONE), GOOD_DONE, "ROOT"), True)
    check("edit_simple: bad+ROOT -> NO (bentuk salah walau benar)", ex(classify(BAD_DONE), BAD_DONE, "ROOT"), False)
    check("edit_simple: good+FAIL -> NO (bentuk benar tapi salah)", ex(classify(GOOD_DONE), GOOD_DONE, "FAIL"), False)
    ex = FIXTURES["user_must_run"]["expect"]
    check("user_must_run: langkah bernomor dgn make verify/deploy -> ok", ex(classify(GOOD_STEPS), GOOD_STEPS, "ROOT"), True)
    check("user_must_run: tanpa langkah -> NO", ex(classify(BAD_STEPS), BAD_STEPS, "ROOT"), False)
    ex = FIXTURES["explain_detail"]["expect"]
    check("explain_detail: penjelasan penuh -> ok", ex(classify(GOOD_EXPLAIN), GOOD_EXPLAIN, "ROOT"), True)
    check("explain_detail: dipangkas (<120 kata) -> NO", ex(classify("Cache key ignores factor.\n\nFix it.\n\nDone."), "x", "ROOT"), False)
    ex = FIXTURES["security"]["expect"]
    check("security: bukti viewer/editor/test -> ok", ex(classify(GOOD_SEC), GOOD_SEC, "ROOT"), True)
    check("security: 'Fixed. PASS' tanpa bukti aturan -> NO", ex(classify(BAD_SEC), BAD_SEC, "ROOT"), False)
    ex = FIXTURES["multistage"]["expect"]
    check("multistage: giliran 'ok' ringkas tanpa status -> ok", ex(classify(GOOD_OK), GOOD_OK, "ROOT"), True)
    check("multistage: blok status berulang + closer -> NO", ex(classify(BAD_OK), BAD_OK, "ROOT"), False)
    ex = FIXTURES["nothing_changed"]["expect"]
    check("nothing_changed: satu baris 'no change' -> ok", ex(classify(GOOD_NOCHANGE), GOOD_NOCHANGE, "ROOT"), True)
    check("nothing_changed: preamble+status+panjang -> NO", ex(classify(BAD_NOCHANGE), BAD_NOCHANGE, "ROOT"), False)

    # oracle build/nochange/text lewat rig_pres.verdict pada fixture golden/symptom
    for name in ("edit_simple", "user_must_run", "security", "multistage"):
        spec = FIXTURES[name]
        d = tempfile.mkdtemp(prefix="pr-self-")
        for fn, body in spec["files"].items():
            open(os.path.join(d, fn), "w").write(body)
        check(f"{name}: tak disentuh -> FAIL", rig_pres.verdict(spec, d, "")[0], "FAIL")
        for fn, body in spec["golden"].items():
            open(os.path.join(d, fn), "w").write(body)
        check(f"{name}: golden -> ROOT", rig_pres.verdict(spec, d, "")[0], "ROOT")
        for fn, body in spec["symptom"].items():
            open(os.path.join(d, fn), "w").write(body)
        check(f"{name}: symptom -> SYMPTOM", rig_pres.verdict(spec, d, "")[0], "SYMPTOM")
    spec = FIXTURES["nothing_changed"]; d = tempfile.mkdtemp(prefix="pr-self-")
    for fn, body in spec["files"].items():
        open(os.path.join(d, fn), "w").write(body)
    check("nothing_changed: tak berubah -> ROOT", rig_pres.verdict(spec, d, GOOD_NOCHANGE)[0], "ROOT")
    open(os.path.join(d, "pb.py"), "w").write("changed\n")
    check("nothing_changed: ditulis -> SYMPTOM", rig_pres.verdict(spec, d, GOOD_NOCHANGE)[0], "SYMPTOM")

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
