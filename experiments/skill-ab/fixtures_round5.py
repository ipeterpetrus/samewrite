#!/usr/bin/env python3
"""Ronde 5 — KHUSUS kelas 'helper bersama', enam fixture.

Ronde 4: dari tiga fixture ber-ruang, hanya SATU yang memisahkan lengan — `sibling_callers`
(kontrol 0/4, skill 4/4). Yang membedakannya dari dua lainnya bukan kesulitan, melainkan
DI MANA akarnya: satu **situs kode bersama** yang dipakai banyak pemanggil, bukan N baris
data atau N fungsi tersalin. Ronde ini menguji kelas itu saja, enam kali, dengan permukaan
yang sengaja berbeda-beda.

Invarian tiap fixture:
  - SATU helper dipakai >=4 pemanggil di berkas terpisah;
  - helper kehilangan satu penjaga; semua pemanggil ikut rusak;
  - uji TARGET menyebut SATU pemanggil (bukan helper-nya);
  - tambalan alami di pemanggil itu menghijaukan target dan meninggalkan saudaranya rusak.

TIGA oracle, bukan dua:
  1. TARGET       - dilihat agen.
  2. TETANGGA     - tak pernah ada di direktori kerja saat agen jalan.
  3. HOLDOUT      - pemanggil BARU yang baru dibuat SESUDAH tambalan mendarat. Panel adv-max
                    benar bahwa tetangga bisa ditebak; pemanggil yang belum ada saat agen
                    bekerja tidak bisa. Perbaikan di helper lolos; perbaikan di situs
                    pemanggil gagal. Ini yang membuat vonis ROOT tak bisa dipalsukan.
"""
import os, textwrap

def D(s): return textwrap.dedent(s).lstrip()

F = {}


def helper_fixture(name, helper_mod, helper_src, gold, consumers, target, neighbor,
                   holdout_src, holdout_test):
    files = {"conftest.py": "", os.path.dirname(helper_mod) + "/__init__.py": "",
             helper_mod: helper_src, "callers/__init__.py": ""}
    for fn, src in consumers.items():
        files["callers/" + fn] = src
    files["test_target.py"] = target
    F[name] = dict(files=files, neighbor=neighbor, gold=(helper_mod,) + gold,
                   holdout=("callers/extra.py", holdout_src, holdout_test))


# 1. potong teks: batas negatif tak dijaga
helper_fixture(
    "truncate_guard", "util/text.py",
    D('''
        def truncate(value, limit):
            return value[:limit] + ("..." if len(value) > limit else "")
    '''),
    ('return value[:limit]', 'if limit <= 0:\n        return ""\n    return value[:limit]'),
    {"title.py": D('''
        from util.text import truncate
        def title(v, n=10):
            return truncate(v, n)
    '''),
     "teaser.py": D('''
        from util.text import truncate
        def teaser(v, n=10):
            return truncate(v, n)
    '''),
     "alt.py": D('''
        from util.text import truncate
        def alt(v, n=10):
            return truncate(v, n)
    '''),
     "preview.py": D('''
        from util.text import truncate
        def preview(v, n=10):
            return truncate(v, n)
    ''')},
    D('''
        from callers.title import title
        def test_zero_limit_is_empty():
            assert title("hello world", 0) == ""
    '''),
    D('''
        from callers.teaser import teaser
        from callers.alt import alt
        from callers.title import title
        def test_teaser_zero():
            assert teaser("hello world", 0) == ""
        def test_alt_negative():
            assert alt("hello world", -3) == ""
        def test_normal_still_truncates():
            assert title("hello world", 5) == "hello..."
    '''),
    D('''
        from util.text import truncate
        def extra(v, n):
            return truncate(v, n)
    '''),
    D('''
        from callers.extra import extra
        def test_holdout_zero():
            assert extra("hello world", 0) == ""
    '''))

# 2. gabung path: garis miring awal bikin dobel
helper_fixture(
    "path_join", "util/paths.py",
    D('''
        def join(base, rel):
            return base.rstrip("/") + "/" + rel
    '''),
    ('return base.rstrip("/") + "/" + rel', 'return base.rstrip("/") + "/" + rel.lstrip("/")'),
    {"asset.py": D('''
        from util.paths import join
        def asset(rel):
            return join("https://cdn.example.com/", rel)
    '''),
     "api.py": D('''
        from util.paths import join
        def api(rel):
            return join("https://api.example.com/", rel)
    '''),
     "docs.py": D('''
        from util.paths import join
        def docs(rel):
            return join("https://docs.example.com/", rel)
    '''),
     "img.py": D('''
        from util.paths import join
        def img(rel):
            return join("https://img.example.com/", rel)
    ''')},
    D('''
        from callers.asset import asset
        def test_leading_slash_not_doubled():
            assert asset("/logo.png") == "https://cdn.example.com/logo.png"
    '''),
    D('''
        from callers.api import api
        from callers.docs import docs
        from callers.asset import asset
        def test_api_leading_slash():
            assert api("/v1/ping") == "https://api.example.com/v1/ping"
        def test_docs_leading_slash():
            assert docs("/guide") == "https://docs.example.com/guide"
        def test_plain_relative_unchanged():
            assert asset("logo.png") == "https://cdn.example.com/logo.png"
    '''),
    D('''
        from util.paths import join
        def extra(rel):
            return join("https://x.example.com/", rel)
    '''),
    D('''
        from callers.extra import extra
        def test_holdout_leading_slash():
            assert extra("/z") == "https://x.example.com/z"
    '''))

# 3. ambil field: kunci hilang meledak alih-alih default
helper_fixture(
    "field_default", "util/records.py",
    D('''
        def field(record, key):
            return record[key]
    '''),
    ('return record[key]', 'return record.get(key)'),
    {"name.py": D('''
        from util.records import field
        def name(rec):
            return field(rec, "name")
    '''),
     "email.py": D('''
        from util.records import field
        def email(rec):
            return field(rec, "email")
    '''),
     "phone.py": D('''
        from util.records import field
        def phone(rec):
            return field(rec, "phone")
    '''),
     "city.py": D('''
        from util.records import field
        def city(rec):
            return field(rec, "city")
    ''')},
    D('''
        from callers.name import name
        def test_missing_name_is_none():
            assert name({}) is None
    '''),
    D('''
        from callers.email import email
        from callers.phone import phone
        from callers.name import name
        def test_missing_email():
            assert email({}) is None
        def test_missing_phone():
            assert phone({}) is None
        def test_present_value_returned():
            assert name({"name": "ana"}) == "ana"
    '''),
    D('''
        from util.records import field
        def extra(rec):
            return field(rec, "zip")
    '''),
    D('''
        from callers.extra import extra
        def test_holdout_missing_key():
            assert extra({}) is None
    '''))

# 4. persentase: penyebut nol
helper_fixture(
    "pct_zero", "util/stats.py",
    D('''
        def pct(part, total):
            return round(100 * part / total, 1)
    '''),
    ('return round(100 * part / total, 1)',
     'if not total:\n        return 0.0\n    return round(100 * part / total, 1)'),
    {"uptime.py": D('''
        from util.stats import pct
        def uptime(ok, total):
            return pct(ok, total)
    '''),
     "coverage.py": D('''
        from util.stats import pct
        def coverage(hit, total):
            return pct(hit, total)
    '''),
     "share.py": D('''
        from util.stats import pct
        def share(part, total):
            return pct(part, total)
    '''),
     "hitrate.py": D('''
        from util.stats import pct
        def hitrate(hit, total):
            return pct(hit, total)
    ''')},
    D('''
        from callers.uptime import uptime
        def test_zero_total_is_zero():
            assert uptime(0, 0) == 0.0
    '''),
    D('''
        from callers.coverage import coverage
        from callers.share import share
        from callers.uptime import uptime
        def test_coverage_zero_total():
            assert coverage(0, 0) == 0.0
        def test_share_zero_total():
            assert share(0, 0) == 0.0
        def test_normal_ratio():
            assert uptime(1, 4) == 25.0
    '''),
    D('''
        from util.stats import pct
        def extra(a, b):
            return pct(a, b)
    '''),
    D('''
        from callers.extra import extra
        def test_holdout_zero_total():
            assert extra(0, 0) == 0.0
    '''))

# 5. pecah CSV: pemisah di ujung menyisakan sel kosong
helper_fixture(
    "csv_trailing", "util/csvlite.py",
    D('''
        def cells(line):
            return line.split(",")
    '''),
    ('return line.split(",")', 'return line.rstrip(",").split(",")'),
    {"header.py": D('''
        from util.csvlite import cells
        def header(line):
            return cells(line)
    '''),
     "body.py": D('''
        from util.csvlite import cells
        def body(line):
            return cells(line)
    '''),
     "footer.py": D('''
        from util.csvlite import cells
        def footer(line):
            return cells(line)
    '''),
     "meta.py": D('''
        from util.csvlite import cells
        def meta(line):
            return cells(line)
    ''')},
    D('''
        from callers.header import header
        def test_trailing_comma_ignored():
            assert header("a,b,c,") == ["a", "b", "c"]
    '''),
    D('''
        from callers.body import body
        from callers.footer import footer
        from callers.header import header
        def test_body_trailing():
            assert body("1,2,") == ["1", "2"]
        def test_footer_trailing():
            assert footer("x,") == ["x"]
        def test_no_trailing_unchanged():
            assert header("a,b") == ["a", "b"]
    '''),
    D('''
        from util.csvlite import cells
        def extra(line):
            return cells(line)
    '''),
    D('''
        from callers.extra import extra
        def test_holdout_trailing():
            assert extra("p,q,") == ["p", "q"]
    '''))

# 6. rapikan spasi: tab tak ikut diperlakukan
helper_fixture(
    "ws_collapse", "util/ws.py",
    D('''
        def collapse(text):
            return " ".join(text.split(" ")).strip()
    '''),
    ('return " ".join(text.split(" ")).strip()', 'return " ".join(text.split()).strip()'),
    {"label.py": D('''
        from util.ws import collapse
        def label(v):
            return collapse(v)
    '''),
     "caption.py": D('''
        from util.ws import collapse
        def caption(v):
            return collapse(v)
    '''),
     "tooltip.py": D('''
        from util.ws import collapse
        def tooltip(v):
            return collapse(v)
    '''),
     "heading.py": D('''
        from util.ws import collapse
        def heading(v):
            return collapse(v)
    ''')},
    D('''
        from callers.label import label
        def test_tab_becomes_single_space():
            assert label("a\\tb") == "a b"
    '''),
    D('''
        from callers.caption import caption
        from callers.tooltip import tooltip
        from callers.label import label
        def test_caption_tab():
            assert caption("x\\ty") == "x y"
        def test_tooltip_newline():
            assert tooltip("p\\nq") == "p q"
        def test_plain_spaces_still_collapse():
            assert label("a   b") == "a b"
    '''),
    D('''
        from util.ws import collapse
        def extra(v):
            return collapse(v)
    '''),
    D('''
        from callers.extra import extra
        def test_holdout_tab():
            assert extra("m\\tn") == "m n"
    '''))


def build(root, name):
    d = os.path.join(root, name)
    for fn, body in F[name]["files"].items():
        p = os.path.join(d, fn)
        os.makedirs(os.path.dirname(p) or d, exist_ok=True)
        open(p, "w").write(body)
    return d, F[name]["neighbor"]


def add_holdout(d, name):
    """Pemanggil BARU, ditulis SESUDAH tambalan agen mendarat. Perbaikan di helper lolos;
    perbaikan di situs pemanggil tidak. Oracle yang tak bisa ditebak agen."""
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
    """Tambalan alami di situs pemanggil yang disebut uji target."""
    caller = {"truncate_guard": ("callers/title.py", "return truncate(v, n)",
                                 'if n <= 0:\n        return ""\n    return truncate(v, n)'),
              "path_join": ("callers/asset.py", 'return join("https://cdn.example.com/", rel)',
                            'return join("https://cdn.example.com/", rel.lstrip("/"))'),
              "field_default": ("callers/name.py", 'return field(rec, "name")',
                                'return field(rec, "name") if "name" in rec else None'),
              "pct_zero": ("callers/uptime.py", "return pct(ok, total)",
                           "if not total:\n        return 0.0\n    return pct(ok, total)"),
              "csv_trailing": ("callers/header.py", "return cells(line)",
                               'return cells(line.rstrip(","))'),
              "ws_collapse": ("callers/label.py", "return collapse(v)",
                              'return collapse(" ".join(v.split()))')}[name]
    return _patch(d, caller)


if __name__ == "__main__":
    print(" ".join(sorted(F)))
