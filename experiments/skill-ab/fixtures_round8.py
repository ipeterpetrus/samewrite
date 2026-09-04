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
       "kembalikan dict. test_target.py harus lulus.",
   ask_en="Implement report(path): read that CSV, sum the hours column per dept, "
          "return a dict. test_target.py must pass.")

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
       "60 detik yang menggeser; now adalah detik. test_target.py harus lulus.",
   ask_en="Implement allow(key, now): allow at most 3 calls per key within a sliding "
          "60 second window; now is in seconds. test_target.py must pass.")

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
       "test_target.py harus lulus.",
   ask_en="Implement call(fn, sleeper): try fn up to 4 times; between attempts call "
          "sleeper(seconds) with backoff 1, 2, 4. Re-raise if all fail. "
          "test_target.py must pass.")

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
       "test_target.py harus lulus.",
   ask_en="Implement register(name) as a decorator that registers a function, and "
          "dispatch(name, value) that calls it; an unknown name raises KeyError. "
          "test_target.py must pass.")


F["config_merge"] = dict(files={
    "mod.py": D('''
        def merge(base, override):
            raise NotImplementedError
    '''),
    "test_target.py": D('''
        from mod import merge
        def test_right_wins():
            assert merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}
        def test_nested_merges_not_replaces():
            assert merge({"db": {"host": "h", "port": 1}}, {"db": {"port": 2}}) \
                   == {"db": {"host": "h", "port": 2}}
        def test_inputs_untouched():
            a = {"db": {"port": 1}}
            merge(a, {"db": {"port": 2}})
            assert a == {"db": {"port": 1}}
    '''),
}, ask="Implementasikan merge(base, override): gabungkan dua dict config bersarang, "
       "nilai override menang, dict di dalamnya digabung bukan diganti, dan kedua "
       "masukan tidak boleh berubah. test_target.py harus lulus.",
   ask_en="Implement merge(base, override): combine two nested config dicts, override "
          "wins, dicts inside are merged rather than replaced, and neither input may "
          "be mutated. test_target.py must pass.")

F["path_router"] = dict(files={
    "mod.py": D('''
        def route(pattern, path):
            raise NotImplementedError
    '''),
    "test_target.py": D('''
        from mod import route
        def test_static():
            assert route("/users/list", "/users/list") == {}
        def test_param():
            assert route("/users/<id>", "/users/42") == {"id": "42"}
        def test_two_params():
            assert route("/a/<x>/b/<y>", "/a/1/b/2") == {"x": "1", "y": "2"}
        def test_no_match():
            assert route("/users/<id>", "/posts/42") is None
        def test_length_mismatch():
            assert route("/users/<id>", "/users/42/edit") is None
    '''),
}, ask="Implementasikan route(pattern, path): cocokkan path dengan pola bersegmen; "
       "segmen <nama> menangkap nilainya. Kembalikan dict tangkapan, atau None kalau "
       "tak cocok. test_target.py harus lulus.",
   ask_en="Implement route(pattern, path): match a path against a segmented pattern; "
          "a <name> segment captures its value. Return a dict of captures, or None if "
          "it does not match. test_target.py must pass.")


def build(root, name):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    for fn, body in F[name]["files"].items():
        open(os.path.join(d, fn), "w").write(body)
    return d


if __name__ == "__main__":
    print(" ".join(sorted(F)))
