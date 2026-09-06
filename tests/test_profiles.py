#!/usr/bin/env python3
"""Uji tools/profiles.py: penemuan lintas-profil, argumen direktori, dedup, dan
laporan cakupan. Berdiri sendiri — jalankan berkas ini, tanpa runner."""
import json, os, subprocess, sys, tempfile

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
sys.path.insert(0, TOOLS)
import profiles  # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


def mkprofile(root, name, n_proj=1, n_files=1):
    """Bentuk nyata di disk: <root>/<name>/projects/<proj>/<sid>.jsonl"""
    made = []
    for pi in range(n_proj):
        d = os.path.join(root, name, "projects", f"-p{pi}")
        os.makedirs(d, exist_ok=True)
        for fi in range(n_files):
            p = os.path.join(d, f"s{fi}.jsonl")
            # tiga turn, bukan satu: carry = ukuran x turn TERSISA, jadi sesi satu-turn
            # carry-nya nol dan uji "ditemukan" akan lulus lewat jalur kosong.
            rec = json.dumps({"type": "assistant",
                              "message": {"usage": {"output_tokens": 1},
                                          "content": [{"type": "text", "text": "x" * 100}]}})
            open(p, "w").write((rec + "\n") * 3)
            made.append(p)
    return made


def main():
    with tempfile.TemporaryDirectory() as home:
        a = mkprofile(home, ".claude", n_proj=2, n_files=2)          # 4
        b = mkprofile(home, ".claude-pro", n_proj=1, n_files=3)      # 3
        c = mkprofile(home, ".config/claude", n_proj=1, n_files=1)   # 1

        env_home = dict(os.environ, HOME=home)
        env_home.pop("CLAUDE_CONFIG_DIR", None)

        old_home, old_cfg = os.environ.get("HOME"), os.environ.pop("CLAUDE_CONFIG_DIR", None)
        os.environ["HOME"] = home
        try:
            dirs = profiles.config_dirs()
            # Sanity fixture: kalau HOME tak berpengaruh, seluruh uji di bawah mengukur mesin
            # nyata dan "lulus" tanpa arti.
            check("fixture: config_dirs mengikuti HOME",
                  all(d.startswith(home) for d in dirs), True)

            paths, roots = profiles.resolve([])
            check("menemukan ketiga profil", len(roots), 3)
            check("menemukan semua transcript", len(paths), len(a) + len(b) + len(c))
            check("laporan menyebut jumlah profil", "3 profile(s)" in
                  profiles.note(paths, roots, False), True)

            # CLAUDE_CONFIG_DIR menang urutannya
            os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(home, ".claude-pro")
            _, roots2 = profiles.resolve([])
            check("CLAUDE_CONFIG_DIR jadi profil pertama",
                  os.path.realpath(roots2[0]), os.path.realpath(os.path.join(home, ".claude-pro")))
            del os.environ["CLAUDE_CONFIG_DIR"]

            # argumen direktori: profil utuh
            paths3, roots3 = profiles.resolve([os.path.join(home, ".claude")])
            check("argumen direktori = seluruh profilnya", len(paths3), len(a))
            check("direktori tercatat sebagai root", len(roots3), 1)

            # direktori tanpa layout projects/ tetap ditelusuri
            flat = os.path.join(home, "flat")
            os.makedirs(flat)
            open(os.path.join(flat, "z.jsonl"), "w").write("{}\n")
            check("direktori datar ikut ditelusuri", len(profiles.resolve([flat])[0]), 1)

            # dedup lintas jalur (symlink profil kedua ke arsip yang sama)
            link = os.path.join(home, ".claude-mirror")
            os.symlink(os.path.join(home, ".claude"), link)
            paths4, _ = profiles.resolve([])
            check("symlink tak menggandakan transcript", len(paths4), len(a) + len(b) + len(c))

            # berkas eksplisit lewat apa adanya, walau tak ada
            check("berkas yang disebut lewat apa adanya",
                  profiles.resolve(["/tak/ada/x.jsonl"])[0], ["/tak/ada/x.jsonl"])
        finally:
            if old_home is not None:
                os.environ["HOME"] = old_home
            if old_cfg is not None:
                os.environ["CLAUDE_CONFIG_DIR"] = old_cfg

        # jalur konsumen: carry.py tanpa argumen sama sekali
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "carry.py"),
                            "--min-turns", "1"],
                           capture_output=True, text=True, env=env_home)
        check("carry.py tanpa argumen menemukan sesi", "sessions=8" in r.stdout, True)
        check("cakupan dilaporkan ke stderr, bukan stdout",
              "profile(s)" in r.stderr and "profile(s)" not in r.stdout, True)

        # jalur konsumen: skills.py menerima direktori profil
        r2 = subprocess.run([sys.executable, os.path.join(TOOLS, "skills.py"),
                             os.path.join(home, ".claude")],
                            capture_output=True, text=True, env=env_home)
        check("skills.py menerima direktori (nol listing = pesan, bukan crash)",
              r2.returncode, 1)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
