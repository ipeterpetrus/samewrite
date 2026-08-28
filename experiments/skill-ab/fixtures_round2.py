#!/usr/bin/env python3
"""Ronde 2: bug MULTI-BERKAS dengan LOKUS MENYESATKAN.

Ronde 1 gagal karena efek langit-langit — kedua lengan menyelesaikan 18/18. Di sini
gejalanya muncul di berkas yang BUKAN penyebabnya, sehingga pembacaan dangkal menambal
tempat yang salah. Perbaikan-gejala tetap membuat TARGET hijau dan TETANGGA merah.
"""
import os, textwrap

def D(s): return textwrap.dedent(s).lstrip()

F = {}

# 1. Gejala di parser, akar di normalizer yang membuang tanda minus.
F["wrong_locus"] = dict(files={
    "normalize.py": D('''
        def normalize(raw):
            """Rapikan input pengguna sebelum di-parse."""
            return raw.strip().replace(" ", "").lstrip("-+")
    '''),
    "parser.py": D('''
        from normalize import normalize

        def parse_amount(raw):
            text = normalize(raw)
            return int(text)
    '''),
    "test_target.py": D('''
        from parser import parse_amount
        def test_negative():
            assert parse_amount(" -42 ") == -42
    '''),
}, neighbor=D('''
    from normalize import normalize
    from parser import parse_amount
    def test_normalize_keeps_spacing_rule():
        assert normalize(" 1 2 ") == "12"
    def test_plus_sign_still_parses():
        assert parse_amount("+7") == 7
    def test_positive():
        assert parse_amount(" 42 ") == 42
'''))

# 2. Keadaan modul dibagi antar instans: lulus sendirian, gagal berpasangan.
F["shared_state"] = dict(files={
    "store.py": D('''
        _ITEMS = []

        class Basket:
            def __init__(self):
                self.items = _ITEMS

            def add(self, name):
                self.items.append(name)
                return self

            def count(self):
                return len(self.items)
    '''),
    "test_target.py": D('''
        from store import Basket
        def test_two_baskets_independent():
            a = Basket(); a.add("x")
            b = Basket()
            assert b.count() == 0
    '''),
}, neighbor=D('''
    from store import Basket
    def test_add_returns_self():
        assert Basket().add("y").count() == 1
    def test_three_baskets():
        Basket().add("p"); Basket().add("q")
        assert Basket().count() == 0
'''))

# 3. Uang disimpan float; gejala muncul sebagai selisih 1 sen di laporan.
F["money_float"] = dict(files={
    "ledger.py": D('''
        class Ledger:
            def __init__(self):
                self.total = 0.0

            def add(self, amount):
                self.total += amount
                return self.total
    '''),
    "report.py": D('''
        from ledger import Ledger

        def summarise(amounts):
            led = Ledger()
            for a in amounts:
                led.add(a)
            return led.total
    '''),
    "test_target.py": D('''
        from report import summarise
        def test_three_dimes():
            assert summarise([0.10, 0.10, 0.10]) == 0.30
    '''),
}, neighbor=D('''
    from report import summarise
    def test_many_cents():
        assert summarise([0.01] * 100) == 1.00
    def test_mixed():
        assert summarise([0.70, 0.20, 0.10]) == 1.00
'''))

# 4. Nama lokal menutupi fungsi modul; galat "not callable" menunjuk pemanggil.
F["shadowing"] = dict(files={
    "util.py": D('''
        def clean(text):
            return text.strip()

        def apply(items):
            clean = []
            for it in items:
                clean.append(clean(it))
            return clean
    '''),
    "test_target.py": D('''
        from util import apply
        def test_apply_strips():
            assert apply([" a ", " b "]) == ["a", "b"]
    '''),
}, neighbor=D('''
    from util import apply, clean
    def test_clean_still_exported():
        assert clean("  z  ") == "z"
    def test_empty():
        assert apply([]) == []
'''))

# 5. super() salah arah: gejala muncul di kelas cucu, akar di kelas dasar.
F["inheritance"] = dict(files={
    "base.py": D('''
        class Node:
            def __init__(self, name):
                self.name = name
                self.tags = []

            def describe(self):
                return self.name
    '''),
    "shapes.py": D('''
        from base import Node

        class Tagged(Node):
            def __init__(self, name, tags):
                Node.__init__(self, name)
                self.tags = tags

            def describe(self):
                return f"{self.name}[{','.join(self.tags)}]"

        class Leaf(Tagged):
            def __init__(self, name, tags, value):
                Tagged.__init__(self, name, tags)
                self.value = value

            def describe(self):
                return Node.describe(self) + f"={self.value}"
    '''),
    "test_target.py": D('''
        from shapes import Leaf
        def test_leaf_keeps_tags():
            assert Leaf("n", ["a"], 3).describe() == "n[a]=3"
    '''),
}, neighbor=D('''
    from shapes import Tagged, Leaf
    def test_tagged_unchanged():
        assert Tagged("t", ["x", "y"]).describe() == "t[x,y]"
    def test_leaf_no_tags():
        assert Leaf("m", [], 1).describe() == "m[]=1"
'''))

# 6. Regex rakus; gejala tampak seperti masalah pemotongan string.
F["greedy_regex"] = dict(files={
    "tags.py": D('''
        import re

        PATTERN = re.compile(r"<(.+)>")

        def first_tag(text):
            m = PATTERN.search(text)
            return m.group(1) if m else None
    '''),
    "test_target.py": D('''
        from tags import first_tag
        def test_two_tags():
            assert first_tag("<a><b>") == "a"
    '''),
}, neighbor=D('''
    from tags import first_tag
    def test_single():
        assert first_tag("<solo>") == "solo"
    def test_none():
        assert first_tag("plain") is None
    def test_three():
        assert first_tag("<x><y><z>") == "x"
'''))


def build(root, name):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    for fn, body in F[name]["files"].items():
        open(os.path.join(d, fn), "w").write(body)
    return d, F[name]["neighbor"]


if __name__ == "__main__":
    print(" ".join(sorted(F)))
