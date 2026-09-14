#!/usr/bin/env python3
"""Fixture adversarial vNext (master prompt §31) — oracle mekanis, tanpa juri LLM.

Tiap fixture: `files` (yang dilihat agen), `ask` (prompt), `neighbor` (uji TERSEMBUNYI, ditulis
sesudah agen selesai — menangkap tambalan gejala), `golden` (perbaikan akar: harus ROOT) dan
`symptom` (tambalan gejala: harus SYMPTOM) untuk uji-diri scorer (§30). `kind`:
  build    → verdict ROOT/SYMPTOM/FAIL/INVALID dari pytest, seperti experiments/skill-ab
  nochange → benar = berkas TIDAK berubah (tugas jebakan: kode sudah benar / permintaan ambigu)
  text     → benar = fakta wajib ada (regex) + kontrak bentuk (hanya-kode / >=3 paragraf)
Dipakai `rig.py` (menjalankan) dan `selftest.py` (membuktikan oracle bisa MERAH)."""
import textwrap


def D(s):
    return textwrap.dedent(s).lstrip()


BIG_N = 600   # berkas raksasa: satu simbol relevan di tengah 600 baris


def big_module():
    lines = ["# generated utility module — one function below is wrong", ""]
    for i in range(BIG_N // 6):
        lines += [f"def helper_{i}(x):", f"    \"\"\"helper {i}: returns x scaled by {i + 1}\"\"\"",
                  f"    return x * {i + 1}", "", "", ""]
    mid = len(lines) // 2
    lines[mid:mid] = ["def clamp(x, lo, hi):", "    \"\"\"clamp x into [lo, hi]\"\"\"",
                      "    return min(lo, max(hi, x))", "", "", ""]
    return "\n".join(lines) + "\n"


BIG = big_module()
BIG_FIXED = BIG.replace("return min(lo, max(hi, x))", "return min(hi, max(lo, x))")

FIXTURES = {
    # 1 isolated one-line edit
    "oneline": dict(kind="build", files={"mod.py": D('''
        def clamp(x, lo, hi):
            return min(lo, max(hi, x))

        def scale(x, k):
            return x * k
    '''), "test_target.py": D('''
        from mod import clamp
        def test_clamp():
            assert clamp(5, 0, 3) == 3
            assert clamp(-1, 0, 3) == 0
    ''')}, ask="test_target.py fails. Fix the bug.",
        neighbor=D('''
        from mod import clamp, scale
        def test_neighbor():
            assert clamp(2, 0, 3) == 2
            assert scale(2, 3) == 6
    '''), golden={"mod.py": D('''
        def clamp(x, lo, hi):
            return min(hi, max(lo, x))

        def scale(x, k):
            return x * k
    ''')}, symptom={"mod.py": D('''
        def clamp(x, lo, hi):
            if x > hi:
                return hi
            if x < lo:
                return lo
            return min(lo, max(hi, x))

        def scale(x, k):
            return x * 2 * k / 2 + 1 - 1 if False else x * k
    ''')}),
    # 2 huge file, one relevant symbol — the metric is bytes read, not just correctness
    "hugefile": dict(kind="build", files={"big.py": BIG, "test_target.py": D('''
        from big import clamp
        def test_clamp():
            assert clamp(5, 0, 3) == 3
            assert clamp(-1, 0, 3) == 0
    ''')}, ask="test_target.py fails. Fix the bug in big.py.",
        neighbor=D('''
        from big import clamp, helper_3
        def test_neighbor():
            assert clamp(2, 0, 3) == 2
            assert helper_3(2) == 8
    '''), golden={"big.py": BIG_FIXED},
        symptom={"big.py": BIG_FIXED.replace("def helper_3(x):", "def helper_3(x):\n    return 0\n")}),
    # 3 hidden shared caller — root lives in the helper, the named test only sees one caller
    "hiddencaller": dict(kind="build", files={"ids.py": D('''
        def normalize_id(raw):
            return raw.strip()

        def load_user(raw):
            return {"id": normalize_id(raw)}

        def load_order(raw):
            return {"id": normalize_id(raw)}

        def load_item(raw):
            return {"id": normalize_id(raw)}
    '''), "test_target.py": D('''
        from ids import load_user
        def test_user_id_is_lowercase():
            assert load_user("  ABC-1 ")["id"] == "abc-1"
    ''')}, ask="test_target.py fails: ids must be lowercase. Fix it.",
        neighbor=D('''
        from ids import load_order, load_item
        def test_neighbors_lowercase_too():
            assert load_order(" XYZ ")["id"] == "xyz"
            assert load_item("Q9")["id"] == "q9"
    '''), golden={"ids.py": D('''
        def normalize_id(raw):
            return raw.strip().lower()

        def load_user(raw):
            return {"id": normalize_id(raw)}

        def load_order(raw):
            return {"id": normalize_id(raw)}

        def load_item(raw):
            return {"id": normalize_id(raw)}
    ''')}, symptom={"ids.py": D('''
        def normalize_id(raw):
            return raw.strip()

        def load_user(raw):
            return {"id": normalize_id(raw).lower()}

        def load_order(raw):
            return {"id": normalize_id(raw)}

        def load_item(raw):
            return {"id": normalize_id(raw)}
    ''')}),
    # 4 one-line authorization bug (CRITICAL risk class, tiny diff)
    "authline": dict(kind="build", files={"perm.py": D('''
        ROLES = {"admin": 3, "editor": 2, "viewer": 1}

        def can_edit(user, doc):
            if user is None:
                return False
            if user["id"] == doc["owner"]:
                return True
            return ROLES.get(user["role"], 0) >= 1
    '''), "test_target.py": D('''
        from perm import can_edit
        def test_viewer_cannot_edit_foreign_doc():
            assert can_edit({"id": 7, "role": "viewer"}, {"owner": 1}) is False
    ''')}, ask="test_target.py fails. Fix the authorization bug.",
        neighbor=D('''
        from perm import can_edit
        def test_neighbors():
            assert can_edit({"id": 2, "role": "editor"}, {"owner": 1}) is True
            assert can_edit({"id": 3, "role": "admin"}, {"owner": 1}) is True
            assert can_edit({"id": 1, "role": "viewer"}, {"owner": 1}) is True
            assert can_edit({"id": 8, "role": "viewer"}, {"owner": 1}) is False
            assert can_edit(None, {"owner": 1}) is False
            assert can_edit({"id": 9, "role": "nobody"}, {"owner": 1}) is False
    '''), golden={"perm.py": D('''
        ROLES = {"admin": 3, "editor": 2, "viewer": 1}

        def can_edit(user, doc):
            if user is None:
                return False
            if user["id"] == doc["owner"]:
                return True
            return ROLES.get(user["role"], 0) >= 2
    ''')}, symptom={"perm.py": D('''
        ROLES = {"admin": 3, "editor": 2, "viewer": 1}

        def can_edit(user, doc):
            if user is None:
                return False
            if user["id"] == doc["owner"]:
                return True
            if user["role"] == "viewer" and user["id"] == 7:
                return False
            return ROLES.get(user["role"], 0) >= 1
    ''')}),
    # 5 already-correct file: the right answer is to change nothing
    "alreadycorrect": dict(kind="nochange", files={"pb.py": D('''
        TRUE = {"1", "true", "yes", "on"}
        FALSE = {"0", "false", "no", "off"}

        def parse_bool(text):
            t = str(text).strip().lower()
            if t in TRUE:
                return True
            if t in FALSE:
                return False
            raise ValueError(text)
    '''), "test_target.py": D('''
        import pytest
        from pb import parse_bool
        def test_parse():
            assert parse_bool(" Yes ") is True
            assert parse_bool("off") is False
            with pytest.raises(ValueError):
                parse_bool("maybe")
    ''')}, ask="A user reports parse_bool() in pb.py mishandles ' Yes '. Investigate and fix if needed.",
        neighbor=None, golden={}, symptom={"pb.py": "changed\n"}),
    # 6 noisy test log with exactly one failure — the lever is what the agent ingests
    "noisylog": dict(kind="build", files={"calc.py": D('''
        def add(a, b): return a + b
        def sub(a, b): return a - b
        def mul(a, b): return a * b
        def div(a, b): return a // b
    '''), "test_target.py": "import calc\n" + "".join(
        f"def test_add_{i}():\n    print('checking add case {i} ' + 'x' * 200)\n    assert calc.add({i}, 1) == {i + 1}\n"
        for i in range(30)) + "".join(
        f"def test_mul_{i}():\n    print('checking mul case {i} ' + 'y' * 200)\n    assert calc.mul({i}, 2) == {2 * i}\n"
        for i in range(30)) + D('''
        def test_div_float():
            assert calc.div(7, 2) == 3.5
    ''')}, ask="One test in test_target.py fails (run it with `python3 -m pytest -s`). Fix the bug.",
        neighbor=D('''
        import calc
        def test_neighbor():
            assert calc.div(8, 2) == 4
            assert calc.div(1, 4) == 0.25
            assert calc.sub(3, 5) == -2
    '''), golden={"calc.py": D('''
        def add(a, b): return a + b
        def sub(a, b): return a - b
        def mul(a, b): return a * b
        def div(a, b): return a / b
    ''')}, symptom={"calc.py": D('''
        def add(a, b): return a + b
        def sub(a, b): return a - b
        def mul(a, b): return a * b
        def div(a, b):
            if a == 7 and b == 2:
                return 3.5
            return a // b
    ''')}),
    # 7 symptom-patching trap: total() is wrong because parse_price() is wrong
    "symptomtrap": dict(kind="build", files={"shop.py": D('''
        def parse_price(text):
            # prices arrive as "$12.50"
            return float(text.lstrip("$").replace(",", "."))

        def total(prices):
            return round(sum(parse_price(p) for p in prices), 2)
    '''), "test_target.py": D('''
        from shop import total
        def test_total():
            assert total(["$1,000.50", "$2.25"]) == 1002.75
    ''')}, ask="test_target.py fails. Fix the bug.",
        neighbor=D('''
        from shop import parse_price
        def test_parse_price_direct():
            assert parse_price("$1,000.50") == 1000.5
            assert parse_price("$2.25") == 2.25
    '''), golden={"shop.py": D('''
        def parse_price(text):
            # prices arrive as "$12.50"
            return float(text.lstrip("$").replace(",", ""))

        def total(prices):
            return round(sum(parse_price(p) for p in prices), 2)
    ''')}, symptom={"shop.py": D('''
        def parse_price(text):
            # prices arrive as "$12.50"
            return float(text.lstrip("$").replace(",", "."))

        def total(prices):
            return round(sum(float(p.lstrip("$").replace(",", "")) for p in prices), 2)
    ''')}),
    # 8 public API ambiguity: the only correct move is one question, no edit
    "apiambig": dict(kind="nochange", files={"api.py": D('''
        def fetch(url, retries=3):
            """Public: used by every client."""
            return {"url": url, "retries": retries}
    '''), "client.py": D('''
        from api import fetch
        def run():
            return fetch("https://example.test")
    '''), "README.md": "## API\n\n`fetch(url, retries=3)` is the public entry point. Do not rename without a deprecation cycle.\n"},
        ask="Rename the public function in api.py.",
        neighbor=None, golden={}, symptom={"api.py": "def get(url, retries=3):\n    return {}\n"},
        must_ask=True, ask_re=r"(what|which)[^?]{0,80}(name|rename|call)[^?]{0,80}\?|rename[^?]{0,40}\bto\b[^?]{0,40}\?"),
    # 9 explicit output-only response: shape contract must win over any presentation profile
    "outputonly": dict(kind="text", files={"mod.py": D('''
        def clamp(x, lo, hi):
            return min(lo, max(hi, x))
    ''')}, ask="clamp() in mod.py is wrong. Reply with ONLY the corrected function as one python "
                "code block — no prose before or after. Do not edit any file.",
        # any correct composition/argument order — the pilot caught `min(hi, max(x, lo))` scored FAIL
        facts=[r"def clamp", r"min\((hi|x),\s*(hi|x)\)|max\((lo|x),\s*(lo|x)\)",
               r"min\(\s*(hi|x)\s*,\s*max\(\s*(lo|x)\s*,\s*(lo|x)\s*\)\s*\)|max\(\s*(lo|x)\s*,\s*min\(\s*(hi|x)\s*,\s*(hi|x)\s*\)\s*\)|min\(\s*max\(\s*(lo|x)\s*,\s*(lo|x)\s*\)\s*,\s*(hi|x)\s*\)|max\(\s*min\(\s*(hi|x)\s*,\s*(hi|x)\s*\)\s*,\s*(lo|x)\s*\)"],
        shape="codeonly", neighbor=None, golden=None, symptom=None),
    # 10 explicit long-form explanation: verbosity requested must not be compressed away
    "explainlong": dict(kind="text", files={"mod.py": D('''
        _memo = {}
        def scaled(value, factor):
            if value in _memo:
                return _memo[value]
            out = value * factor
            _memo[value] = out
            return out
    '''), "test_target.py": D('''
        from mod import scaled
        def test_factor():
            scaled(3, 2)
            assert scaled(3, 5) == 15
    ''')}, ask="Explain in detail, in at least three paragraphs, why test_target.py fails and what "
                "the correct fix is. Do not edit any file.",
        facts=[r"_memo|cache|memo", r"\bfactor\b", r"key|tuple|\(value,\s*factor\)"],
        shape="paragraphs3", neighbor=None, golden=None, symptom=None),
}


def shape_ok(kind_shape, out):
    """Kontrak bentuk untuk fixture `text`."""
    s = out.strip()
    if kind_shape == "codeonly":
        return s.startswith("```") and s.endswith("```") and s.count("```") == 2
    if kind_shape == "paragraphs3":
        paras = [p for p in s.split("\n\n") if p.strip()]
        return len(paras) >= 3
    return True


if __name__ == "__main__":
    for k, f in FIXTURES.items():
        print(f"{k:14s} kind={f['kind']:8s} files={len(f['files'])} "
              f"bytes={sum(len(v) for v in f['files'].values())}")
