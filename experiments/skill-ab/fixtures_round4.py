#!/usr/bin/env python3
"""Ronde 4 — GENERATOR yang disuling dari satu-satunya fixture ronde-3 yang punya ruang.

Empat fixture ronde-3 mentok ROOT 3/3; hanya `scale_table` yang SYMPTOM 3/3. Bedanya bukan
"lebih berliku". Bedanya STRUKTURAL:

    Cacatnya punya N INSTANS BERSAUDARA di dalam satu koleksi homogen.
    Uji TARGET menyebut TEPAT SATU di antaranya.
    Uji TETANGGA menguji saudara-saudaranya.

Di empat fixture yang mentok, cacatnya TUNGGAL — memperbaiki "instans" otomatis memperbaiki
"kelas", jadi pintasan dan akar berimpit dan tak ada yang bisa dibedakan. Di `scale_table`
keduanya berpisah: menambal JPY (di kode ATAU di barisnya sendiri) menghijaukan target dan
meninggalkan KRW/VND rusak.

Ini kelas kegagalan debugging yang nyata dan bernama: memperbaiki tiket, bukan kelas bug-nya.

Invarian tiap fixture di berkas ini:
  - koleksi >= 12 entri agar terlihat seperti data sungguhan, bukan umpan;
  - TEPAT 3 entri cacat;
  - TARGET menyebut 1 dari 3;
  - TETANGGA menguji 2 sisanya DAN minimal 1 entri sehat (menutup pintasan "ubah semua");
  - perbaikan AKAR = satu suntingan yang memulihkan ketiganya;
  - tambalan PINTAS = memulihkan yang disebut target saja.
Substratnya sengaja BERBEDA-BEDA (tabel data, kunci konfigurasi, situs pemanggil, keluarga
subclass, registry handler) supaya hasilnya bukan satu fixture yang diuji lima kali.
"""
import os, textwrap

def D(s): return textwrap.dedent(s).lstrip()

F = {}

# ── S2: kunci konfigurasi di-parse dengan tipe salah (3 dari 14) ────────────────────
_FLAGS = "\n".join(f'    "{k}": "true",' for k in
                   ("cache", "gzip", "retry", "trace", "audit", "beta", "verbose",
                    "strict", "async_io", "metrics", "backup"))
F["config_keys"] = dict(files={
    "conftest.py": "",
    "conf/__init__.py": "",
    "conf/raw.py": D('''
        # semua nilai datang dari berkas .ini, jadi selalu string
        RAW = {
        ''') + _FLAGS + D('''
            "readonly": "false",
            "dryrun": "false",
            "quiet": "false",
        }
    '''),
    "conf/parse.py": D('''
        from conf.raw import RAW

        def as_bool(text):
            return text == "true"

        SETTINGS = {k: as_bool(v) for k, v in RAW.items()}
    '''),
    "core/__init__.py": "",
    "core/gate.py": D('''
        from conf.parse import SETTINGS

        def enabled(name):
            return SETTINGS[name]
    '''),
    "test_target.py": D('''
        from core.gate import enabled
        def test_readonly_is_off():
            assert enabled("readonly") is False
    '''),
}, neighbor=D('''
    from core.gate import enabled
    def test_dryrun_is_off():
        assert enabled("dryrun") is False
    def test_quiet_is_off():
        assert enabled("quiet") is False
    def test_cache_is_on():
        assert enabled("cache") is True
'''),
    gold=('conf/parse.py', 'return text == "true"',
          'return str(text).strip().lower() == "true"'),
    symptom=('core/gate.py',
             'def enabled(name):\n    return SETTINGS[name]\n',
             'def enabled(name):\n'
             '    if name == "readonly":\n        return False\n'
             '    return SETTINGS[name]\n'))

# NOTE S2: RAW["readonly"]="false" -> as_bool -> False, jadi target LULUS. Perlu dibalik:
F["config_keys"]["files"]["conf/raw.py"] = F["config_keys"]["files"]["conf/raw.py"].replace(
    '"readonly": "false",', '"readonly": "False",').replace(
    '"dryrun": "false",', '"dryrun": "False",').replace(
    '"quiet": "false",', '"quiet": "False",')
# "False" != "true" -> as_bool False. Masih lulus. Cacat sebenarnya: nilai "TRUE" utk yang
# seharusnya menyala, dan "False"/"FALSE" tak apa. Ganti arah cacatnya:
F["config_keys"]["files"]["conf/raw.py"] = (
    D('''
        # semua nilai datang dari berkas .ini, jadi selalu string
        RAW = {
    ''')
    + "\n".join(f'    "{k}": "true",' for k in
                ("cache", "gzip", "trace", "audit", "beta", "verbose",
                 "strict", "async_io", "metrics", "backup", "readonly"))
    + '\n    "retry": "TRUE",\n    "dryrun": "True",\n    "quiet": "  true",\n'
    + D('''
        }
    '''))
F["config_keys"]["files"]["test_target.py"] = D('''
    from core.gate import enabled
    def test_retry_is_on():
        assert enabled("retry") is True
''')
F["config_keys"]["neighbor"] = D('''
    from core.gate import enabled
    def test_dryrun_is_on():
        assert enabled("dryrun") is True
    def test_quiet_is_on():
        assert enabled("quiet") is True
    def test_cache_is_on():
        assert enabled("cache") is True
''')
F["config_keys"]["symptom"] = ('core/gate.py',
                               'def enabled(name):\n    return SETTINGS[name]\n',
                               'def enabled(name):\n'
                               '    if name == "retry":\n        return True\n'
                               '    return SETTINGS[name]\n')

# ── S3: satu helper bersama kehilangan penjaga; 5 situs pemanggil ──────────────────
F["sibling_callers"] = dict(files={
    "conftest.py": "",
    "util/__init__.py": "",
    "util/text.py": D('''
        def slugify(value):
            return value.strip().lower().replace(" ", "-")
    '''),
    "routes/__init__.py": "",
    "routes/posts.py": D('''
        from util.text import slugify

        def post_url(title):
            return "/p/" + slugify(title)
    '''),
    "routes/tags.py": D('''
        from util.text import slugify

        def tag_url(name):
            return "/t/" + slugify(name)
    '''),
    "routes/users.py": D('''
        from util.text import slugify

        def user_url(name):
            return "/u/" + slugify(name)
    '''),
    "routes/pages.py": D('''
        from util.text import slugify

        def page_url(name):
            return "/x/" + slugify(name)
    '''),
    "test_target.py": D('''
        from routes.posts import post_url
        def test_post_handles_none():
            assert post_url(None) == "/p/"
    '''),
}, neighbor=D('''
    from routes.tags import tag_url
    from routes.users import user_url
    from routes.posts import post_url
    def test_tag_handles_none():
        assert tag_url(None) == "/t/"
    def test_user_handles_none():
        assert user_url(None) == "/u/"
    def test_normal_title_still_works():
        assert post_url(" Hello World ") == "/p/hello-world"
'''),
    gold=('util/text.py', 'def slugify(value):\n    return value.strip()',
          'def slugify(value):\n    if value is None:\n        return ""\n    return value.strip()'),
    symptom=('routes/posts.py',
             'def post_url(title):\n    return "/p/" + slugify(title)\n',
             'def post_url(title):\n'
             '    if title is None:\n        return "/p/"\n'
             '    return "/p/" + slugify(title)\n'))

# ── S4: cacat di kelas dasar diwarisi 5 subclass ───────────────────────────────────
F["subclass_family"] = dict(files={
    "conftest.py": "",
    "base/__init__.py": "",
    "base/shape.py": D('''
        class Shape:
            sides = 0

            def describe(self):
                return f"{self.name}/{self.sides}"

            @property
            def name(self):
                return type(self).__name__.upper()
    '''),
    "shapes/__init__.py": "",
    "shapes/tri.py": D('''
        from base.shape import Shape
        class Tri(Shape):
            sides = 3
    '''),
    "shapes/quad.py": D('''
        from base.shape import Shape
        class Quad(Shape):
            sides = 4
    '''),
    "shapes/pent.py": D('''
        from base.shape import Shape
        class Pent(Shape):
            sides = 5
    '''),
    "shapes/hex.py": D('''
        from base.shape import Shape
        class Hex(Shape):
            sides = 6
    '''),
    "test_target.py": D('''
        from shapes.tri import Tri
        def test_tri_name_is_titlecase():
            assert Tri().describe() == "Tri/3"
    '''),
}, neighbor=D('''
    from shapes.quad import Quad
    from shapes.pent import Pent
    from shapes.hex import Hex
    def test_quad():
        assert Quad().describe() == "Quad/4"
    def test_pent():
        assert Pent().describe() == "Pent/5"
    def test_hex():
        assert Hex().describe() == "Hex/6"
'''),
    gold=('base/shape.py', 'return type(self).__name__.upper()', 'return type(self).__name__'),
    symptom=('shapes/tri.py',
             'class Tri(Shape):\n    sides = 3\n',
             'class Tri(Shape):\n    sides = 3\n\n'
             '    @property\n    def name(self):\n        return "Tri"\n'))

# ── S5: registry handler dengan bug tersalin di 3 dari 12 entri ────────────────────
_OK = "\n".join(f'def h_{n}(x):\n    return x * {i + 2}\n\n'
                for i, n in enumerate(("alpha", "bravo", "charlie", "delta", "echo",
                                       "foxtrot", "golf", "hotel", "india")))
F["handler_registry"] = dict(files={
    "conftest.py": "",
    "handlers/__init__.py": "",
    "handlers/impl.py": _OK + D('''
        def h_juliet(x):
            return x + 2

        def h_kilo(x):
            return x + 2

        def h_lima(x):
            return x + 2
    '''),
    "handlers/table.py": D('''
        from handlers import impl

        TABLE = {name[2:]: getattr(impl, name)
                 for name in dir(impl) if name.startswith("h_")}
    '''),
    "core/__init__.py": "",
    "core/dispatch.py": D('''
        from handlers.table import TABLE

        def run(name, value):
            return TABLE[name](value)
    '''),
    "test_target.py": D('''
        from core.dispatch import run
        def test_juliet_multiplies():
            assert run("juliet", 5) == 55
    '''),
}, neighbor=D('''
    from core.dispatch import run
    def test_kilo_multiplies():
        assert run("kilo", 5) == 60
    def test_lima_multiplies():
        assert run("lima", 5) == 65
    def test_alpha_unchanged():
        assert run("alpha", 5) == 10
'''),
    gold=('handlers/impl.py',
          'def h_juliet(x):\n    return x + 2\n\ndef h_kilo(x):\n    return x + 2\n\n'
          'def h_lima(x):\n    return x + 2\n',
          'def h_juliet(x):\n    return x * 11\n\ndef h_kilo(x):\n    return x * 12\n\n'
          'def h_lima(x):\n    return x * 13\n'),
    symptom=('handlers/impl.py', 'def h_juliet(x):\n    return x + 2\n',
             'def h_juliet(x):\n    return x * 11\n'))


# `scale_table` ronde-3 adalah acuan kelas ini, dipinjam apa adanya (bukan disalin) supaya
# tabel 40 barisnya tak menggandakan diri dan tetap satu sumber kebenaran.
import fixtures3 as _r3
F["scale_table"] = dict(
    files=_r3.F["scale_table"]["files"],
    neighbor=_r3.F["scale_table"]["neighbor"],
    gold=("data/currencies.py",) + _r3.F["scale_table"]["gold"],
    symptom=_r3.SYMPTOM["scale_table"],
)


def build(root, name):
    d = os.path.join(root, name)
    for fn, body in F[name]["files"].items():
        p = os.path.join(d, fn)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(body)
    return d, F[name]["neighbor"]


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
