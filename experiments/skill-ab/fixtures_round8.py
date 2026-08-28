#!/usr/bin/env python3
"""Ronde 8 — tugas ponytail yang BESAR, supaya ada ruang untuk over-engineering.

Ronde 7 nol sinyal karena langit-langit: keempat tugas selesai dalam 2-3 baris dan NOL
abstraksi baru di semua lengan. Tak ada yang over-engineer, jadi tak ada yang bisa dicegah.

Di sini tiap tugas: (a) solusi minimal masih wajar (15-30 baris), (b) versi over-engineered
sangat menggoda dan lazim di dunia nyata (kelas, strategy, dataclass, dekorator, ABC), dan
(c) ujinya memaku PERILAKU saja, bukan bentuk — jadi yang minimal tetap lulus.

Ukuran (gerbang benar dulu: pytest hijau):
  baris bertambah · def/class baru (AST) · berkas baru · impor baru
"""
import os, textwrap

def D(s): return textwrap.dedent(s).lstrip()

F = {}

F["csv_report"] = dict(files={
    "data.csv": "dept,name,hours\neng,ana,8\nops,bo,5\neng,cy,7\nops,di,9\neng,ed,3\n",
    "mod.py": D('''
        def report(path):
            raise NotImplementedError
    '''),
    "test_target.py": D('''
        from mod import report
        def test_grouped_totals():
            assert report("data.csv") == {"eng": 18, "ops": 14}
        def test_empty(tmp_path):
            p = tmp_path / "e.csv"
            p.write_text("dept,name,hours\\n")
            assert report(str(p)) == {}
    '''),
}, ask="Implementasikan report(path): baca CSV itu, jumlahkan kolom hours per dept, "
       "kembalikan dict. test_target.py harus lulus.")

F["rate_limiter"] = dict(files={
    "mod.py": D('''
        def allow(key, now):
            raise NotImplementedError
    '''),
    "test_target.py": D('''
        from mod import allow
        def test_under_limit():
            assert allow("a", 0) is True
            assert allow("a", 1) is True
            assert allow("a", 2) is True
        def test_over_limit():
            for t in range(3):
                allow("b", t)
            assert allow("b", 3) is False
        def test_window_slides():
            for t in range(3):
                allow("c", t)
            assert allow("c", 61) is True
        def test_keys_independent():
            for t in range(3):
                allow("d", t)
            assert allow("e", 3) is True
    '''),
}, ask="Implementasikan allow(key, now): izinkan maksimal 3 panggilan per key dalam jendela "
       "60 detik yang menggeser; now adalah detik. test_target.py harus lulus.")

F["retry_backoff"] = dict(files={
    "mod.py": D('''
        def call(fn, sleeper):
            raise NotImplementedError
    '''),
    "test_target.py": D('''
        import pytest
        from mod import call
        def test_succeeds_first():
            waits = []
            assert call(lambda: "ok", waits.append) == "ok"
            assert waits == []
        def test_retries_with_backoff():
            state = {"n": 0}
            waits = []
            def flaky():
                state["n"] += 1
                if state["n"] < 3:
                    raise RuntimeError("x")
                return "ok"
            assert call(flaky, waits.append) == "ok"
            assert waits == [1, 2]
        def test_gives_up_after_four():
            waits = []
            def always():
                raise RuntimeError("x")
            with pytest.raises(RuntimeError):
                call(always, waits.append)
            assert waits == [1, 2, 4]
    '''),
}, ask="Implementasikan call(fn, sleeper): coba fn hingga 4 kali; di antara percobaan panggil "
       "sleeper(detik) dengan backoff 1, 2, 4. Lempar ulang bila semua gagal. "
       "test_target.py harus lulus.")

F["plugin_registry"] = dict(files={
    "mod.py": D('''
        def register(name):
            raise NotImplementedError

        def dispatch(name, value):
            raise NotImplementedError
    '''),
    "test_target.py": D('''
        import pytest
        from mod import register, dispatch
        def test_register_and_dispatch():
            @register("double")
            def d(v):
                return v * 2
            assert dispatch("double", 4) == 8
        def test_unknown_raises():
            with pytest.raises(KeyError):
                dispatch("nope", 1)
        def test_decorator_returns_function():
            @register("id")
            def f(v):
                return v
            assert f(3) == 3
    '''),
}, ask="Implementasikan register(name) sebagai dekorator yang mendaftarkan fungsi, dan "
       "dispatch(name, value) yang memanggilnya; nama tak dikenal melempar KeyError. "
       "test_target.py harus lulus.")


def build(root, name):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    for fn, body in F[name]["files"].items():
        open(os.path.join(d, fn), "w").write(body)
    return d


if __name__ == "__main__":
    print(" ".join(sorted(F)))
