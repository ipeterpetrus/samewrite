#!/usr/bin/env python3
"""Uji-diri instrumen (master prompt §30): sebelum satu run berbayar pun, buktikan scorer
membedakan BAIK dari BURUK.  GOOD fixture → GREEN · CONTROLLED BAD fixture → RED.

  1. oracle build: golden → ROOT; symptom → SYMPTOM; tak disentuh → FAIL; uji diedit → INVALID
  2. oracle nochange: tak berubah (+ tanya bila wajib) → ROOT; ditulis → SYMPTOM; tak tanya → FAIL
  3. oracle text: fakta lengkap + bentuk benar → ROOT; fakta kurang / bentuk salah → FAIL
  4. ekstraktor metrik: transcript sintetis → usage, byte per sumber, giliran yang benar
  5. pemeriksa perlakuan: banner asing di lengan A → treatment_ok False; banner yang diharapkan
     hilang di lengan E → False; tepat → True
Berdiri sendiri; nol panggilan model."""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rig  # noqa: E402
from fixtures import FIXTURES  # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


def mk(spec, patch=None):
    d = tempfile.mkdtemp(prefix="vn-self-")
    for fn, body in spec["files"].items():
        open(os.path.join(d, fn), "w").write(body)
    for fn, body in (patch or {}).items():
        open(os.path.join(d, fn), "w").write(body)
    return d


def main():
    for name, spec in FIXTURES.items():
        if spec["kind"] == "build":
            check(f"{name}: tak disentuh -> FAIL", rig.verdict(spec, mk(spec), "")[0], "FAIL")
            check(f"{name}: golden -> ROOT", rig.verdict(spec, mk(spec, spec["golden"]), "")[0], "ROOT")
            check(f"{name}: symptom -> SYMPTOM", rig.verdict(spec, mk(spec, spec["symptom"]), "")[0], "SYMPTOM")
            check(f"{name}: uji disunting -> INVALID",
                  rig.verdict(spec, mk(spec, dict(spec["golden"], **{"test_target.py": "def test_x(): pass\n"})), "")[0], "INVALID")
        elif spec["kind"] == "nochange":
            need_q = spec.get("must_ask", False)
            check(f"{name}: tak berubah{' + tanya' if need_q else ''} -> ROOT",
                  rig.verdict(spec, mk(spec), "Which name? ")[0], "ROOT")
            check(f"{name}: ditulis -> SYMPTOM", rig.verdict(spec, mk(spec, spec["symptom"]), "done")[0], "SYMPTOM")
            dd = mk(spec); os.makedirs(os.path.join(dd, ".pytest_cache")); os.makedirs(os.path.join(dd, "__pycache__"))
            open(os.path.join(dd, "_stdout.txt"), "w").write("x")
            check(f"{name}: artefak alat (.pytest_cache/__pycache__/_stdout) bukan berkas baru -> ROOT",
                  rig.verdict(spec, dd, "Which name? ")[0], "ROOT")
            if need_q:
                check(f"{name}: tak tanya -> FAIL", rig.verdict(spec, mk(spec), "Renamed it.")[0], "FAIL")
        else:
            good = {"outputonly": "```python\ndef clamp(x, lo, hi):\n    return min(hi, max(lo, x))\n```",
                    "explainlong": "The _memo cache is keyed by value only.\n\nSo factor is ignored on the "
                                   "second call.\n\nFix: key the cache by the tuple (value, factor)."}[name]
            bad_shape = {"outputonly": "Here is the fix:\n```python\ndef clamp(x, lo, hi):\n    return min(hi, max(lo, x))\n```",
                         "explainlong": "The _memo cache ignores factor; key it by (value, factor)."}[name]
            bad_fact = {"outputonly": "```python\ndef clamp(x, lo, hi):\n    return x\n```",
                        "explainlong": "It fails.\n\nBecause of a bug.\n\nFix the bug."}[name]
            check(f"{name}: fakta+bentuk -> ROOT", rig.verdict(spec, mk(spec), good)[0], "ROOT")
            check(f"{name}: bentuk salah -> FAIL", rig.verdict(spec, mk(spec), bad_shape)[0], "FAIL")
            check(f"{name}: fakta kurang -> FAIL", rig.verdict(spec, mk(spec), bad_fact)[0], "FAIL")
            check(f"{name}: berkas diubah -> FAIL", rig.verdict(spec, mk(spec, {"mod.py": "x\n"}), good)[0], "FAIL")
            if name == "outputonly":
                for body in ("min(hi, max(x, lo))", "max(lo, min(hi, x))", "min(max(lo, x), hi)", "max(min(x, hi), lo)"):
                    check(f"{name}: urutan argumen lain yang benar {body} -> ROOT",
                          rig.verdict(spec, mk(spec), "```python\ndef clamp(x, lo, hi):\n    return " + body + "\n```")[0], "ROOT")
                check(f"{name}: komposisi salah min(lo, max(hi, x)) -> FAIL",
                      rig.verdict(spec, mk(spec), "```python\ndef clamp(x, lo, hi):\n    return min(lo, max(hi, x))\n```")[0], "FAIL")

    # 4. ekstraktor metrik pada transcript sintetis
    d = tempfile.mkdtemp(prefix="vn-tp-")
    tp = os.path.join(d, "s.jsonl")
    lines = [
        {"type": "attachment", "attachment": {"type": "skill_listing", "content": "- dataviz: built-in\n- samewrite: Precision layer for code changes"}},
        {"type": "user", "message": {"content": "fix it"}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "1", "name": "Read", "input": {"file_path": "x"}}],
                                          "usage": {"input_tokens": 10, "cache_read_input_tokens": 1000,
                                                    "cache_creation_input_tokens": 100, "output_tokens": 20}}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "1", "content": "A" * 500}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "2", "name": "Bash", "input": {"command": "pytest"}}],
                                          "usage": {"input_tokens": 5, "cache_read_input_tokens": 2000,
                                                    "cache_creation_input_tokens": 50, "output_tokens": 30}}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "2", "content": "B" * 300}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "DONE"}],
                                          "usage": {"input_tokens": 1, "cache_read_input_tokens": 3000,
                                                    "cache_creation_input_tokens": 0, "output_tokens": 5}}},
    ]
    open(tp, "w").write("\n".join(json.dumps(x) for x in lines) + "\n")
    m = rig.metrics(tp, "D")
    check("metrik: usage dijumlahkan", m["usage"]["cache_read_input_tokens"], 6000)
    check("metrik: output dijumlahkan", m["usage"]["output_tokens"], 55)
    check("metrik: Read bytes tercatat", m["bytes_by_source"].get("Read", 0) >= 500, True)
    check("metrik: Bash bytes tercatat", m["bytes_by_source"].get("Bash", 0) >= 300, True)
    check("metrik: giliran = 3", m["turns"], 3)
    check("metrik: weighted_input = in + 1.25cc + 0.1cr", round(m["weighted_input"], 1), round(16 + 1.25 * 150 + 0.1 * 6000, 1))
    check("perlakuan D: listing samewrite ada, nol banner asing -> ok", m["treatment_ok"], True)
    check("perlakuan A: entri samewrite di listing -> BAD", rig.metrics(tp, "A")["treatment_ok"], False)
    check("metrik: tool_counts dari blok tool_use saja", m["tool_counts"], {"Read": 1, "Bash": 1})
    tp2 = os.path.join(d, "a.jsonl")
    open(tp2, "w").write(json.dumps({"type": "attachment", "attachment": {"type": "skill_listing",
                                     "content": "- dataviz: built-in only"}}) + "\n")
    check("perlakuan A: hanya skill bawaan CLI -> ok", rig.metrics(tp2, "A")["treatment_ok"], True)
    check("perlakuan C: listing tanpa edit-discipline -> BAD", rig.metrics(tp2, "C")["treatment_ok"], False)
    check("perlakuan E: banner ponytail absen -> BAD", rig.metrics(tp, "E")["treatment_ok"], False)
    open(tp, "a").write(json.dumps({"type": "attachment", "attachment": {"type": "hook", "content": "PONYTAIL MODE ACTIVE — level: full"}}) + "\n")
    check("perlakuan H: banner ponytail + listing samewrite -> ok", rig.metrics(tp, "H")["treatment_ok"], True)
    check("perlakuan D dengan banner ponytail nyasar -> BAD", rig.metrics(tp, "D")["treatment_ok"], False)
    shutil.rmtree(d, ignore_errors=True)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
