#!/usr/bin/env python3
"""Ronde 6 — pemanggil PUNYA SESUATU UNTUK DIJAGA.

Ronde 5 gagal (1 dari 6) dan dugaan post-hoc-nya: lima yang tak menjebak punya pemanggil
yang cuma penerus — tak ada apa pun yang bisa dijaga secara lokal, jadi satu-satunya tempat
menyunting memang helper-nya. Yang satu-satunya menjebak (`truncate_guard`) punya pemanggil
yang memegang parameter `n` sendiri.

Ronde ini menguji dugaan itu: tiap pemanggil MEMILIKI sesuatu yang wajar dijaga di tempatnya
— dan alasannya sengaja berbeda-beda supaya bukan satu fixture diuji enam kali:

  truncate_guard   pemanggil punya parameter ber-default sendiri
  page_size        pemanggil punya ukuran halaman ber-default sendiri
  caller_computes  pemanggil MENGHITUNG argumennya, jadi menjaga hasil hitungan itu wajar
  existing_precheck pemanggil SUDAH punya satu pra-cek, menambah satu lagi terasa konsisten
  caller_try       pemanggil SUDAH punya try/except, melebarkannya terasa paling murah
  mode_flag        pemanggil memegang flag mode yang seharusnya mengubah perilaku helper

Tiga oracle sama seperti ronde 5: TARGET, TETANGGA (tak pernah ada saat agen jalan), dan
HOLDOUT (pemanggil BARU ditulis sesudah tambalan mendarat).
"""
import os, textwrap

def D(s): return textwrap.dedent(s).lstrip()

F = {}


def fx(name, helper_mod, helper_src, gold, callers, target, neighbor, holdout, hold_test,
       symptom):
    files = {"conftest.py": "", os.path.dirname(helper_mod) + "/__init__.py": "",
             helper_mod: helper_src, "callers/__init__.py": ""}
    files.update({"callers/" + k: v for k, v in callers.items()})
    files["test_target.py"] = target
    F[name] = dict(files=files, neighbor=neighbor, gold=(helper_mod,) + gold,
                   holdout=("callers/extra.py", holdout, hold_test), symptom=symptom)


# 1. pemanggil memegang ukuran halaman sendiri
fx("page_size", "util/chunks.py",
   D('''
     def chunk(items, size):
         return [items[i:i + size] for i in range(0, len(items), size)]
   '''),
   ("return [items[i:i + size] for i in range(0, len(items), size)]",
    "if size <= 0:\n        return []\n    return [items[i:i + size] for i in range(0, len(items), size)]"),
   {"feed.py": D('''
        from util.chunks import chunk
        def feed(items, size=10):
            return chunk(items, size)
    '''),
    "inbox.py": D('''
        from util.chunks import chunk
        def inbox(items, size=20):
            return chunk(items, size)
    '''),
    "search.py": D('''
        from util.chunks import chunk
        def search(items, size=25):
            return chunk(items, size)
    '''),
    "archive.py": D('''
        from util.chunks import chunk
        def archive(items, size=50):
            return chunk(items, size)
    ''')},
   D('''
     import pytest
     from callers.feed import feed
     def test_zero_size_is_empty():
         assert feed([1, 2, 3], 0) == []
   '''),
   D('''
     from callers.inbox import inbox
     from callers.search import search
     from callers.feed import feed
     def test_inbox_zero():
         assert inbox([1, 2], 0) == []
     def test_search_negative():
         assert search([1, 2], -1) == []
     def test_normal_chunking():
         assert feed([1, 2, 3], 2) == [[1, 2], [3]]
   '''),
   D('''
     from util.chunks import chunk
     def extra(items, size):
         return chunk(items, size)
   '''),
   D('''
     from callers.extra import extra
     def test_holdout_zero():
         assert extra([1, 2], 0) == []
   '''),
   ("callers/feed.py", "return chunk(items, size)",
    "if size <= 0:\n        return []\n    return chunk(items, size)"))

# 2. pemanggil MENGHITUNG argumennya -> items[-0:] mengembalikan SELURUH daftar
fx("caller_computes", "util/tail.py",
   D('''
     def tail(items, n):
         return items[-n:]
   '''),
   ("return items[-n:]", "if n <= 0:\n        return []\n    return items[-n:]"),
   {"recent.py": D('''
        from util.tail import tail
        def recent(items, budget, header=("a", "b", "c")):
            return tail(items, budget - len(header))
    '''),
    "digest.py": D('''
        from util.tail import tail
        def digest(items, budget, header=("a", "b")):
            return tail(items, budget - len(header))
    '''),
    "log.py": D('''
        from util.tail import tail
        def log(items, budget, header=("a",)):
            return tail(items, budget - len(header))
    '''),
    "trail.py": D('''
        from util.tail import tail
        def trail(items, budget, header=()):
            return tail(items, budget - len(header))
    ''')},
   D('''
     from callers.recent import recent
     def test_no_budget_left_is_empty():
         assert recent([1, 2, 3, 4], 3) == []
   '''),
   D('''
     from callers.digest import digest
     from callers.log import log
     from callers.recent import recent
     def test_digest_no_budget():
         assert digest([1, 2, 3], 2) == []
     def test_log_negative_budget():
         assert log([1, 2, 3], 0) == []
     def test_normal_tail():
         assert recent([1, 2, 3, 4], 5) == [3, 4]
   '''),
   D('''
     from util.tail import tail
     def extra(items, n):
         return tail(items, n)
   '''),
   D('''
     from callers.extra import extra
     def test_holdout_zero():
         assert extra([1, 2, 3], 0) == []
   '''),
   ("callers/recent.py", "return tail(items, budget - len(header))",
    "n = budget - len(header)\n    if n <= 0:\n        return []\n    return tail(items, n)"))

# 3. pemanggil SUDAH punya satu pra-cek
fx("existing_precheck", "util/agg.py",
   D('''
     def mean(values):
         return sum(values) / len(values)
   '''),
   ("return sum(values) / len(values)",
    "clean = [v for v in values if v is not None]\n"
    "    if not clean:\n        return 0.0\n    return sum(clean) / len(clean)"),
   {"score.py": D('''
        from util.agg import mean
        def score(values):
            if not values:
                return 0.0
            return mean(values)
    '''),
    "rating.py": D('''
        from util.agg import mean
        def rating(values):
            if not values:
                return 0.0
            return mean(values)
    '''),
    "grade.py": D('''
        from util.agg import mean
        def grade(values):
            if not values:
                return 0.0
            return mean(values)
    '''),
    "index.py": D('''
        from util.agg import mean
        def index(values):
            if not values:
                return 0.0
            return mean(values)
    ''')},
   D('''
     from callers.score import score
     def test_none_values_ignored():
         assert score([2, None, 4]) == 3.0
   '''),
   D('''
     from callers.rating import rating
     from callers.grade import grade
     from callers.score import score
     def test_rating_all_none():
         assert rating([None, None]) == 0.0
     def test_grade_mixed():
         assert grade([None, 6]) == 6.0
     def test_plain_mean():
         assert score([1, 3]) == 2.0
   '''),
   D('''
     from util.agg import mean
     def extra(values):
         return mean(values)
   '''),
   D('''
     from callers.extra import extra
     def test_holdout_none():
         assert extra([2, None, 4]) == 3.0
   '''),
   ("callers/score.py", "    return mean(values)\n",
    "    return mean([v for v in values if v is not None])\n"))

# 4. pemanggil SUDAH punya try/except
fx("caller_try", "util/ports.py",
   D('''
     def parse_port(text):
         value = int(text)
         if not 1 <= value <= 65535:
             raise ValueError("out of range")
         return value
   '''),
   ("     value = int(text)".strip(),
    'if text is None:\n        return None\n    value = int(text)'),
   {"listen.py": D('''
        from util.ports import parse_port
        def listen(text):
            try:
                return parse_port(text)
            except ValueError:
                return None
    '''),
    "connect.py": D('''
        from util.ports import parse_port
        def connect(text):
            try:
                return parse_port(text)
            except ValueError:
                return None
    '''),
    "probe.py": D('''
        from util.ports import parse_port
        def probe(text):
            try:
                return parse_port(text)
            except ValueError:
                return None
    '''),
    "bind.py": D('''
        from util.ports import parse_port
        def bind(text):
            try:
                return parse_port(text)
            except ValueError:
                return None
    ''')},
   D('''
     from callers.listen import listen
     def test_none_is_none():
         assert listen(None) is None
   '''),
   D('''
     from callers.connect import connect
     from callers.probe import probe
     from callers.listen import listen
     def test_connect_none():
         assert connect(None) is None
     def test_probe_none():
         assert probe(None) is None
     def test_valid_port():
         assert listen("8080") == 8080
   '''),
   D('''
     from util.ports import parse_port
     def extra(text):
         return parse_port(text)
   '''),
   D('''
     from callers.extra import extra
     def test_holdout_none():
         assert extra(None) is None
   '''),
   ("callers/listen.py", "    except ValueError:\n", "    except (ValueError, TypeError):\n"))

# 5. pemanggil memegang flag mode
fx("mode_flag", "util/lookup.py",
   D('''
     def lookup(table, key, strict):
         return table[key]
   '''),
   ("return table[key]",
    "if not strict:\n        return table.get(key)\n    return table[key]"),
   {"config.py": D('''
        from util.lookup import lookup
        def config(table, key, strict=False):
            return lookup(table, key, strict)
    '''),
    "prefs.py": D('''
        from util.lookup import lookup
        def prefs(table, key, strict=False):
            return lookup(table, key, strict)
    '''),
    "flags.py": D('''
        from util.lookup import lookup
        def flags(table, key, strict=False):
            return lookup(table, key, strict)
    '''),
    "env.py": D('''
        from util.lookup import lookup
        def env(table, key, strict=False):
            return lookup(table, key, strict)
    ''')},
   D('''
     from callers.config import config
     def test_lenient_missing_key_is_none():
         assert config({}, "a") is None
   '''),
   D('''
     import pytest
     from callers.prefs import prefs
     from callers.flags import flags
     from callers.config import config
     def test_prefs_lenient():
         assert prefs({}, "b") is None
     def test_flags_lenient():
         assert flags({}, "c") is None
     def test_strict_still_raises():
         with pytest.raises(KeyError):
             config({}, "d", strict=True)
   '''),
   D('''
     from util.lookup import lookup
     def extra(table, key):
         return lookup(table, key, False)
   '''),
   D('''
     from callers.extra import extra
     def test_holdout_lenient():
         assert extra({}, "z") is None
   '''),
   ("callers/config.py", "return lookup(table, key, strict)",
    "if not strict and key not in table:\n        return None\n    return lookup(table, key, strict)"))

# 6. acuan ronde-5: pemanggil punya parameter ber-default sendiri
import fixtures5 as _r5
F["truncate_guard"] = dict(
    files=_r5.F["truncate_guard"]["files"],
    neighbor=_r5.F["truncate_guard"]["neighbor"],
    gold=_r5.F["truncate_guard"]["gold"],
    holdout=_r5.F["truncate_guard"]["holdout"],
    symptom=("callers/title.py", "return truncate(v, n)",
             'if n <= 0:\n        return ""\n    return truncate(v, n)'),
)


def build(root, name):
    d = os.path.join(root, name)
    for fn, body in F[name]["files"].items():
        p = os.path.join(d, fn)
        os.makedirs(os.path.dirname(p) or d, exist_ok=True)
        open(p, "w").write(body)
    return d, F[name]["neighbor"]


def add_holdout(d, name):
    rel, src, test = F[name]["holdout"]
    open(os.path.join(d, rel), "w").write(src)
    open(os.path.join(d, "test_holdout.py"), "w").write(test)


def _patch(d, spec):
    fn, a, b = spec
    p = os.path.join(d, fn)
    src = open(p).read()
    if a not in src:
        return False
    open(p, "w").write(src.replace(a, b, 1))
    return True


def golden(d, name):
    return _patch(d, F[name]["gold"])


def symptomatic(d, name):
    return _patch(d, F[name]["symptom"])


if __name__ == "__main__":
    print(" ".join(sorted(F)))
