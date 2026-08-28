#!/usr/bin/env python3
"""Rig yang sama, dua skill yang BENAR-BENAR selalu menyala di sesi Peter.

systematic-debugging: nol invokasi dalam 1.409 transcript. caveman dan ponytail: disuntik
SETIAP sesi lewat hook SessionStart (4.664 B + 5.228 B). Merekalah yang layak diuji.

Klaimnya beda, jadi oracle-nya beda — kerangkanya sama: lengan berbeda satu perlakuan,
oracle mekanis tanpa juri LLM, pasangan berpasangan, treatment diverifikasi, lengan
placebo satu-kalimat, pra-registrasi ber-ambang.

  caveman  "-65% token keluaran, seluruh substansi teknis tetap"
           -> tugas MENJELASKAN. Ukur panjang jawaban DAN cakupan fakta wajib (regex).
              Ringkas tanpa substansi = GAGAL, bukan sukses.
  ponytail "diff terpendek yang bekerja, tanpa abstraksi tak diminta"
           -> tugas MENGIMPLEMENTASI. Gerbang benar dulu (pytest hijau), baru ukur baris
              bertambah, berkas baru, def/class baru (AST).

Perlakuan disuntik lewat hook SessionStart di config yang sudah disiapkan — bentuk yang
SAMA dengan produksi, dan terlihat di transcript sehingga bisa diverifikasi.
"""
import argparse, ast, json, os, re, subprocess, tempfile, textwrap, time

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.local/bin/claude")
CFG = {"plain": "cfg_plain", "oneline": "cfg_plain",
       "caveman": "cfg_cav", "ponytail": "cfg_pony"}

def D(s): return textwrap.dedent(s).lstrip()

EXPLAIN = {
    "intdiv": dict(files={"mod.py": D('''
        def average(values):
            return sum(values) // len(values)
    '''), "test_target.py": D('''
        from mod import average
        def test_half():
            assert average([1, 2]) == 1.5
    ''')}, facts=[r"//|integer division|pembagian bulat|bilangan bulat", r"\baverage\b",
                  r"(?<!/)/(?!/)|float|desimal|pecahan"]),
    "mutdefault": dict(files={"mod.py": D('''
        def collect(item, acc=[]):
            acc.append(item)
            return acc
    '''), "test_target.py": D('''
        from mod import collect
        def test_twice():
            collect("a")
            assert collect("b") == ["b"]
    ''')}, facts=[r"acc\s*=\s*\[\]|mutable default|default.{0,25}mutable|argumen default",
                  r"\bcollect\b", r"None|dibagi|shared|objek yang sama|dipakai ulang|reuse"]),
    "swallow": dict(files={"mod.py": D('''
        def to_int(text):
            try:
                return int(text)
            except Exception:
                return 0
    '''), "test_target.py": D('''
        import pytest
        from mod import to_int
        def test_raises():
            with pytest.raises(ValueError):
                to_int("abc")
    ''')}, facts=[r"except\s+Exception|menelan|swallow|ditangkap|tertangkap",
                  r"\bto_int\b", r"ValueError"]),
    "cachekey": dict(files={"mod.py": D('''
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
    ''')}, facts=[r"_memo|cache|memo", r"\bfactor\b", r"kunci|key|tuple"]),
}
EXPLAIN_PROMPT = ("Jelaskan kenapa test_target.py gagal dan apa perbaikan yang benar. "
                  "JANGAN menyunting berkas apa pun — cukup jawab.")

BUILD = {
    "memoize": dict(files={"mod.py": D('''
        def slow_square(n):
            return n * n
    '''), "test_target.py": D('''
        from mod import slow_square
        def test_same_result():
            assert slow_square(4) == 16
            assert slow_square(4) == 16
            assert slow_square(5) == 25
    ''')}, ask="Tambahkan caching pada slow_square supaya pemanggilan berulang dengan argumen "
              "sama tidak menghitung ulang. test_target.py harus tetap lulus."),
    "retry": dict(files={"mod.py": D('''
        def fetch(source):
            return source()
    '''), "test_target.py": D('''
        from mod import fetch
        def test_retries_once():
            state = {"n": 0}
            def flaky():
                state["n"] += 1
                if state["n"] == 1:
                    raise RuntimeError("transient")
                return "ok"
            assert fetch(flaky) == "ok"
    ''')}, ask="Buat fetch mencoba ulang SEKALI bila pemanggilan pertama melempar exception. "
              "test_target.py harus lulus."),
    "envconf": dict(files={"mod.py": D('''
        TIMEOUT = 30

        def timeout():
            return TIMEOUT
    '''), "test_target.py": D('''
        import importlib
        def test_env_override(monkeypatch):
            monkeypatch.setenv("APP_TIMEOUT", "5")
            import mod; importlib.reload(mod)
            assert mod.timeout() == 5
        def test_default(monkeypatch):
            monkeypatch.delenv("APP_TIMEOUT", raising=False)
            import mod; importlib.reload(mod)
            assert mod.timeout() == 30
    ''')}, ask="Buat timeout() memakai variabel lingkungan APP_TIMEOUT bila ada, selain itu "
              "tetap 30. test_target.py harus lulus."),
    "validate": dict(files={"mod.py": D('''
        def register(email):
            return {"email": email}
    '''), "test_target.py": D('''
        import pytest
        from mod import register
        def test_ok():
            assert register("a@b.co")["email"] == "a@b.co"
        def test_rejects():
            with pytest.raises(ValueError):
                register("nope")
    ''')}, ask="Tolak email tanpa '@' dengan ValueError di register(). test_target.py harus lulus."),
}

ONELINER = {"caveman": "Jawab sesingkat mungkin, tanpa mengurangi isi teknisnya.",
            "ponytail": "Buat perubahan sekecil mungkin; jangan menambah abstraksi yang tak diminta."}


def defs_count(src):
    try:
        return sum(1 for n in ast.walk(ast.parse(src))
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    except SyntaxError:
        return -1


def run_one(kind, name, arm, model, timeout):
    spec = (EXPLAIN if kind == "caveman" else BUILD)[name]
    work = tempfile.mkdtemp(prefix=f"m-{kind}-{name}-{arm}-")
    d = os.path.join(work, name)
    os.makedirs(d)
    for fn, body in spec["files"].items():
        open(os.path.join(d, fn), "w").write(body)
    cfg = os.path.join(HERE, CFG[kind if arm == "mode" else arm])
    prompt = EXPLAIN_PROMPT if kind == "caveman" else spec["ask"]
    if arm == "oneline":
        prompt = ONELINER[kind] + " " + prompt
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg)
    t0 = time.time()
    try:
        p = subprocess.run([CLAUDE, "-p", prompt, "--model", model,
                            "--permission-mode", "acceptEdits"],
                           cwd=d, capture_output=True, text=True, timeout=timeout, env=env)
        rc, out = p.returncode, (p.stdout or "")
    except subprocess.TimeoutExpired:
        rc, out = -1, ""
    open(os.path.join(d, "_stdout.txt"), "w").write(out)
    res = dict(kind=kind, fixture=name, arm=arm, rc=rc, sec=round(time.time() - t0, 1),
               work=work, cfg=os.path.basename(cfg), chars=len(out),
               words=len(out.split()))
    if kind == "caveman":
        res["facts"] = sum(1 for r in spec["facts"] if re.search(r, out, re.I))
        res["facts_total"] = len(spec["facts"])
    else:
        ok = subprocess.run(["/usr/bin/python3", "-m", "pytest", "-q", "test_target.py"],
                            cwd=d, capture_output=True, timeout=180).returncode
        mp = os.path.join(d, "mod.py")
        cur = open(mp).read() if os.path.exists(mp) else ""
        base = spec["files"]["mod.py"]
        extra = [f for f in os.listdir(d) if f.endswith(".py")
                 and f not in spec["files"] and not f.startswith("_")]
        res.update(passing=(ok == 0),
                   added_lines=max(0, len(cur.splitlines()) - len(base.splitlines())),
                   new_files=len(extra),
                   new_defs=max(0, defs_count(cur) - defs_count(base)))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", required=True, choices=["caveman", "ponytail"])
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--arms", default="plain,oneline,mode")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    names = sorted(EXPLAIN if a.kind == "caveman" else BUILD)
    for r in range(a.repeat):
        for n in names:
            for arm in a.arms.split(","):
                res = run_one(a.kind, n, arm, a.model, a.timeout)
                res.update(rep=r, model=a.model)
                with open(a.out, "a") as fh:
                    fh.write(json.dumps(res) + "\n")
                extra = (f"facts={res.get('facts')}/{res.get('facts_total')}" if a.kind == "caveman"
                         else f"pass={res.get('passing')} +{res.get('added_lines')}baris "
                              f"+{res.get('new_defs')}def +{res.get('new_files')}berkas")
                print(f"{n:12s} {arm:8s} rep{r} rc={res['rc']} {res['sec']}s "
                      f"words={res['words']:>4} {extra}", flush=True)


if __name__ == "__main__":
    main()
