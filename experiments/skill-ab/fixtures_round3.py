#!/usr/bin/env python3
"""Ronde 3 — PRINSIP BARU.

Ronde 1 & 2 mentok di langit-langit. Sebabnya bukan bug-nya kurang berliku, melainkan
berkasnya terlalu sedikit: begitu agen membaca 2-3 berkas kecil, akarnya kelihatan.

Agen berhenti begitu uji TARGET hijau. Jadi ruang-gagal lahir dari SATU kombinasi:
  (a) ada tambalan LOKAL di dekat gejala yang cukup membuat TARGET hijau, dan
  (b) akar sebenarnya berjarak beberapa lompatan, di modul yang TIDAK diimpor langsung
      oleh modul tempat gejala muncul.
Uji TETANGGA memisahkan keduanya. Semua deterministik — nol balapan, nol waktu, nol acak
(panel adv-max membunuh usul fixture nondeterministik: rubrik FAIL/SYMPTOM/ROOT jadi tak
bermakna kalau hasilnya bisa berubah antar-run).
"""
import os, textwrap

def D(s): return textwrap.dedent(s).lstrip()

F = {}

# F1 — satu entri salah di tabel data 40 baris; gejalanya di lapisan API.
_CUR = "\n".join(f'    "{c}": 2,' for c in
                 "USD EUR GBP AUD CAD CHF SEK NOK DKK PLN CZK HUF RON BGN TRY BRL MXN ARS "
                 "CLP COP PEN ZAR NGN EGP AED SAR ILS INR PKR BDT THB PHP MYR SGD HKD TWD "
                 "NZD".split())
F["scale_table"] = dict(files={
    "conftest.py": "",
    "data/__init__.py": "",
    "data/currencies.py": D('''
        # eksponen satuan minor per ISO 4217
        MINOR_UNITS = {
        ''') + _CUR + D('''
            "JPY": 2,
            "KRW": 2,
            "VND": 2,
        }
    '''),
    "services/__init__.py": "",
    "services/money.py": D('''
        from data.currencies import MINOR_UNITS

        def format_amount(code, minor):
            exp = MINOR_UNITS.get(code, 2)
            if exp == 0:
                return f"{minor} {code}"
            return f"{minor / (10 ** exp):.{exp}f} {code}"
    '''),
    "api/__init__.py": "",
    "api/receipt.py": D('''
        from services.money import format_amount

        def line(code, minor):
            return format_amount(code, minor)
    '''),
    "test_target.py": D('''
        from api.receipt import line
        def test_yen_has_no_decimals():
            assert line("JPY", 500) == "500 JPY"
    '''),
}, neighbor=D('''
    from api.receipt import line
    def test_won_has_no_decimals():
        assert line("KRW", 1200) == "1200 KRW"
    def test_dong_has_no_decimals():
        assert line("VND", 90) == "90 VND"
    def test_dollar_keeps_decimals():
        assert line("USD", 500) == "5.00 USD"
'''), gold=('"JPY": 2,\n    "KRW": 2,\n    "VND": 2,',
            '"JPY": 0,\n    "KRW": 0,\n    "VND": 0,'))

# F2 — default bertipe salah di conf/, gejalanya empat lompatan jauhnya.
F["flag_chain"] = dict(files={
    "conftest.py": "",
    "conf/__init__.py": "",
    "conf/defaults.py": D('''
        DEFAULTS = {
            "RETRIES": "0",
            "TIMEOUT": 30,
            "VERIFY": True,
        }
    '''),
    "core/__init__.py": "",
    "core/registry.py": D('''
        from conf.defaults import DEFAULTS

        _REG = dict(DEFAULTS)

        def get(name):
            return _REG[name]
    '''),
    "core/factory.py": D('''
        from core import registry

        def settings():
            return {"retries": registry.get("RETRIES"),
                    "timeout": registry.get("TIMEOUT")}
    '''),
    "handlers/__init__.py": "",
    "handlers/fetch.py": D('''
        from core.factory import settings

        def fetch(source):
            cfg = settings()
            calls = 0
            calls += 1
            source()
            if cfg["retries"]:
                calls += 1
                source()
            return calls
    '''),
    "handlers/push.py": D('''
        from core.factory import settings

        def push(sink):
            cfg = settings()
            calls = 1
            sink()
            if cfg["retries"]:
                calls += 1
                sink()
            return calls
    '''),
    "test_target.py": D('''
        from handlers.fetch import fetch
        def test_no_retry_by_default():
            assert fetch(lambda: None) == 1
    '''),
}, neighbor=D('''
    from handlers.push import push
    from core.factory import settings
    def test_push_also_no_retry():
        assert push(lambda: None) == 1
    def test_retries_is_an_int():
        assert settings()["retries"] == 0
'''), gold=('"RETRIES": "0",', '"RETRIES": 0,'))

# F3 — atribut kelas mutable di kelas dasar; gejalanya di subclass lain.
F["classvar_shared"] = dict(files={
    "conftest.py": "",
    "base/__init__.py": "",
    "base/entity.py": D('''
        class Entity:
            tags = []

            def __init__(self, name):
                self.name = name

            def add_tag(self, tag):
                self.tags.append(tag)
                return self
    '''),
    "models/__init__.py": "",
    "models/user.py": D('''
        from base.entity import Entity

        class User(Entity):
            pass
    '''),
    "models/group.py": D('''
        from base.entity import Entity

        class Group(Entity):
            pass
    '''),
    "models/admin.py": D('''
        from models.user import User

        class Admin(User):
            pass
    '''),
    "test_target.py": D('''
        from models.user import User
        from models.group import Group
        def test_group_not_polluted_by_user():
            User("u").add_tag("a")
            assert Group("g").tags == []
    '''),
}, neighbor=D('''
    from models.user import User
    from models.admin import Admin
    def test_two_users_independent():
        User("a").add_tag("x")
        assert User("b").tags == []
    def test_admin_independent():
        User("a").add_tag("x")
        assert Admin("z").tags == []
'''), gold=('class Entity:\n    tags = []\n\n    def __init__(self, name):\n        self.name = name\n',
            'class Entity:\n    def __init__(self, name):\n        self.name = name\n        self.tags = []\n'))

# F4 — except lebar di helper tingkat rendah; gejalanya nilai default di lapisan aplikasi.
F["swallow_deep"] = dict(files={
    "conftest.py": "",
    "net/__init__.py": "",
    "net/retry.py": D('''
        def call(fn):
            try:
                return fn()
            except Exception:
                return None
    '''),
    "net/client.py": D('''
        from net.retry import call

        DEFAULT = 0

        def get(fn):
            res = call(fn)
            return DEFAULT if res is None else res
    '''),
    "app/__init__.py": "",
    "app/report.py": D('''
        from net.client import get

        def total(fns):
            return sum(get(f) for f in fns)
    '''),
    "app/audit.py": D('''
        from net.client import get

        def check(fn):
            return get(fn)
    '''),
    "test_target.py": D('''
        import pytest
        from app.report import total
        def test_broken_source_propagates():
            def boom():
                raise ValueError("upstream down")
            with pytest.raises(ValueError):
                total([boom])
    '''),
}, neighbor=D('''
    import pytest
    from app.audit import check
    from app.report import total
    def test_audit_also_propagates():
        def boom():
            raise ValueError("upstream down")
        with pytest.raises(ValueError):
            check(boom)
    def test_legit_zero_is_not_an_error():
        assert total([lambda: 0, lambda: 0]) == 0
'''), gold=('    try:\n        return fn()\n    except Exception:\n        return None\n',
            '    return fn()\n'))

# F5 — pembagian pagination kehilangan halaman terakhir; gejalanya di endpoint.
F["pagination_edge"] = dict(files={
    "conftest.py": "",
    "core/__init__.py": "",
    "core/paginate.py": D('''
        def page_count(total, size):
            return total // size

        def slice_for(items, page, size):
            start = page * size
            return items[start:start + size]
    '''),
    "services/__init__.py": "",
    "services/feed.py": D('''
        from core.paginate import page_count, slice_for

        def all_items(items, size):
            out = []
            for p in range(page_count(len(items), size)):
                out.extend(slice_for(items, p, size))
            return out
    '''),
    "api/__init__.py": "",
    "api/listing.py": D('''
        from services.feed import all_items

        def listing(items, size=3):
            return all_items(items, size)
    '''),
    "test_target.py": D('''
        from api.listing import listing
        def test_seven_items_all_returned():
            assert listing(list(range(7)), 3) == list(range(7))
    '''),
}, neighbor=D('''
    from api.listing import listing
    from core.paginate import page_count
    def test_ten_items():
        assert listing(list(range(10)), 3) == list(range(10))
    def test_exact_multiple():
        assert listing(list(range(6)), 3) == list(range(6))
    def test_page_count_rounds_up():
        assert page_count(7, 3) == 3
'''), gold=('return total // size', 'return -(-total // size)'))

# F6 — pengelompokan hilang karena kunci urut salah; gejalanya di laporan.
F["sort_group"] = dict(files={
    "conftest.py": "",
    "data/__init__.py": "",
    "data/rows.py": D('''
        ROWS = [
            {"dept": "eng", "name": "ana"},
            {"dept": "ops", "name": "bo"},
            {"dept": "eng", "name": "cy"},
            {"dept": "ops", "name": "di"},
        ]
    '''),
    "services/__init__.py": "",
    "services/grouping.py": D('''
        def grouped(rows):
            return sorted(rows, key=lambda r: r["name"])
    '''),
    "api/__init__.py": "",
    "api/report.py": D('''
        from services.grouping import grouped

        def render(rows):
            return [f'{r["dept"]}:{r["name"]}' for r in grouped(rows)]
    '''),
    "test_target.py": D('''
        from api.report import render
        from data.rows import ROWS
        def test_departments_stay_together():
            out = render(ROWS)
            assert out == ["eng:ana", "eng:cy", "ops:bo", "ops:di"]
    '''),
}, neighbor=D('''
    from api.report import render
    def test_other_dataset_grouped():
        rows = [{"dept": "z", "name": "a"}, {"dept": "a", "name": "b"},
                {"dept": "z", "name": "c"}, {"dept": "a", "name": "d"}]
        assert render(rows) == ["a:b", "a:d", "z:a", "z:c"]
    def test_single_dept():
        rows = [{"dept": "q", "name": "b"}, {"dept": "q", "name": "a"}]
        assert render(rows) == ["q:a", "q:b"]
'''), gold=('key=lambda r: r["name"]', 'key=lambda r: (r["dept"], r["name"])'))


def build(root, name):
    d = os.path.join(root, name)
    for fn, body in F[name]["files"].items():
        p = os.path.join(d, fn)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(body)
    return d, F[name]["neighbor"]


def golden(d, name):
    """Terapkan perbaikan AKAR. Kontrol positif: rubrik ROOT harus bisa dicapai."""
    a, b = F[name]["gold"]
    for fn in F[name]["files"]:
        p = os.path.join(d, fn)
        src = open(p).read()
        if a in src:
            open(p, "w").write(src.replace(a, b, 1))
            return True
    return False


# KONTROL NEGATIF. Klaim tiap fixture adalah "ada tambalan LOKAL yang membuat TARGET hijau
# tapi TETANGGA merah". Klaim itu harus DIUJI, bukan diasumsikan — kalau tambalan pintasnya
# ternyata setara dengan perbaikan akar, fixture-nya tak bisa membedakan apa pun dan harus
# dibuang. Persis itu yang terjadi pada `sort_group` (mengurutkan string "dept:name" selalu
# mengelompokkan menurut dept karena dept jadi prefiks), jadi ia tidak dipakai.
SYMPTOM = {
    "scale_table": ("api/receipt.py",
                    "def line(code, minor):\n    return format_amount(code, minor)\n",
                    "def line(code, minor):\n"
                    "    if code == \"JPY\":\n"
                    "        return f\"{minor} {code}\"\n"
                    "    return format_amount(code, minor)\n"),
    "flag_chain": ("handlers/fetch.py",
                   "    if cfg[\"retries\"]:\n",
                   "    if int(cfg[\"retries\"]):\n"),
    "classvar_shared": ("models/group.py",
                        "class Group(Entity):\n    pass\n",
                        "class Group(Entity):\n    tags = []\n"),
    "swallow_deep": ("app/report.py",
                     "def total(fns):\n    return sum(get(f) for f in fns)\n",
                     "def total(fns):\n"
                     "    vals = [get(f) for f in fns]\n"
                     "    if any(v == 0 for v in vals):\n"
                     "        raise ValueError(\"upstream down\")\n"
                     "    return sum(vals)\n"),
    "pagination_edge": ("services/feed.py",
                        "    return out\n",
                        "    if len(out) < len(items):\n"
                        "        out.extend(items[len(out):])\n"
                        "    return out\n"),
}


def symptomatic(d, name):
    """Terapkan tambalan PINTAS. Harus: TARGET hijau, TETANGGA merah."""
    fn, a, b = SYMPTOM[name]
    p = os.path.join(d, fn)
    src = open(p).read()
    if a not in src:
        return False
    open(p, "w").write(src.replace(a, b, 1))
    return True


if __name__ == "__main__":
    print(" ".join(sorted(F)))
