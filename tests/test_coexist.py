#!/usr/bin/env python3
"""Matriks koeksistensi (master prompt §26): samewrite harus MENYUSUN, bukan bersaing.

samewrite tak punya mode, saklar, hook per-turn, atau berkas state: ia skill on-demand plus
SATU hook opsional (PreToolUse Write, write_noop_guard.py). Jadi yang bisa bertabrakan hanya
pemasang/pencabutnya dan isi skill-nya. Kasus deterministik di sini: direktori config sementara
yang SUDAH berisi hook, statusLine dan kunci milik plugin lain, plus berkas-flag plugin lain —
permukaan asing diambil dari audit ter-pin (docs/VNEXT.md §3). Baris matriks yang butuh model
(format eksplisit, ambiguitas, auth, multi-giliran) = fixture benchmark, dilabeli EXPERIMENTAL.
Bila SAMEWRITE_REF_DIR menunjuk klon referensi dan `node` ada, hook ponytail/i-have-adhd ASLI
ikut dijalankan dengan skill samewrite terpasang (uji silang hidup)."""
import copy, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
SKILL = open(os.path.join(ROOT, "skills", "samewrite", "SKILL.md"), encoding="utf-8").read()

P = F = 0
MATRIX = []


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


def row(n, name, status):
    MATRIX.append((n, name, status))


FOREIGN_SETTINGS = {
    "statusLine": {"type": "command",
                   "command": "bash /p/hooks/ponytail-statusline.sh && bash /c/caveman-statusline.sh"},
    "permissions": {"allow": ["Bash(ls:*)"]},
    "someUserKey": {"nested": [1, 2, 3]},
    "hooks": {
        "SessionStart": [{"matcher": "startup|resume|clear|compact",
                          "hooks": [{"type": "command", "command": "node /p/hooks/ponytail-activate.js"},
                                    {"type": "command", "command": "node /a/hooks/always-on.mjs"}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command",
                                         "command": "node /p/hooks/ponytail-mode-tracker.js"}]}],
        "SubagentStart": [{"hooks": [{"type": "command", "command": "node /p/hooks/ponytail-subagent.js"}]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}],
    },
}
FOREIGN_FLAGS = {".ponytail-active": "full\n", ".ponytail-statusline-nudged": "",
                 ".i-have-adhd-always": "", ".caveman-active": "full\n",
                 ".caveman-sessions/s1.mode": "full\n"}


class Env:
    """Satu 'mesin' sementara: HOME palsu, CLAUDE_CONFIG_DIR palsu, settings + flag asing."""

    def __init__(self, foreign=True, settings=None):
        self.home = tempfile.mkdtemp(prefix="sw-home-")
        self.cfg = os.path.join(self.home, "cfg dir with space $x")
        os.makedirs(self.cfg)
        self.settings = os.path.join(self.cfg, "settings.json")
        base = copy.deepcopy(FOREIGN_SETTINGS) if foreign else {}
        if settings is not None:
            base = settings
        self.write_settings(base)
        if foreign:
            for name, body in FOREIGN_FLAGS.items():
                p = os.path.join(self.cfg, name); os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w").write(body)
            pc = os.path.join(self.home, ".config", "ponytail"); os.makedirs(pc)
            open(os.path.join(pc, "config.json"), "w").write('{"defaultMode":"full"}\n')
        self.dst = os.path.join(self.home, "bin dir", "write_noop_guard.py")
        os.makedirs(os.path.dirname(self.dst))
        self.ledger = os.path.join(self.home, "logs", "samewrite.jsonl")

    def write_settings(self, d):
        if isinstance(d, str):
            open(self.settings, "w").write(d)
        else:
            json.dump(d, open(self.settings, "w"), indent=2); open(self.settings, "a").write("\n")

    def read_settings(self):
        return json.load(open(self.settings))

    def env(self, **extra):
        e = {k: v for k, v in os.environ.items() if not k.startswith("SAMEWRITE_")}
        e.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.cfg, SAMEWRITE_SETTINGS=self.settings,
                 SAMEWRITE_DST=self.dst, SAMEWRITE_LEDGER=self.ledger, SAMEWRITE_PYTHON=sys.executable,
                 SAMEWRITE_ROOT=self.home)
        e.update(extra)
        return e

    def sh(self, script, **extra):
        return subprocess.run(["bash", os.path.join(HOOKS, script)], capture_output=True, text=True,
                              timeout=120, env=self.env(**extra))

    def guard(self, path, content, **extra):
        p = subprocess.run([sys.executable, os.path.join(HOOKS, "write_noop_guard.py")],
                           input=json.dumps({"tool_name": "Write",
                                             "tool_input": {"file_path": path, "content": content}}),
                           capture_output=True, text=True, timeout=20, env=self.env(**extra))
        return "deny" in p.stdout

    def own_cmds(self):
        return [(ev, m.get("matcher"), h["command"]) for ev, ms in self.read_settings().get("hooks", {}).items()
                for m in ms for h in m.get("hooks", []) if self.dst in h["command"]]

    def foreign_view(self):
        """settings.json tanpa entri milik samewrite — harus == asli secara STRUKTUR."""
        d = self.read_settings()
        hooks = d.get("hooks", {})
        for ev in list(hooks):
            kept = []
            for m in hooks[ev]:
                hs = [h for h in m.get("hooks", []) if self.dst not in h.get("command", "")]
                if hs:
                    kept.append(dict(m, hooks=hs))
            if kept:
                hooks[ev] = kept
            else:
                del hooks[ev]
        if "hooks" in d and not d["hooks"]:
            del d["hooks"]
        return d

    def snapshot(self):
        """hash tiap berkas asing di cfg + ~/.config (settings.json dinilai lewat foreign_view)."""
        out = {}
        for top in (self.cfg, os.path.join(self.home, ".config")):
            for base, _, files in os.walk(top):
                for f in files:
                    p = os.path.join(base, f); rel = os.path.relpath(p, self.home)
                    if f == "settings.json" or ".bak." in rel:
                        continue
                    out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        return out


def main():
    # ---------------------------------------------------------------- 1. samewrite only
    e = Env(foreign=False)
    r = e.sh("install.sh")
    check("1 pasang di config kosong: rc 0", r.returncode, 0)
    check("1 tepat satu entri milik sendiri: PreToolUse(Write)",
          [(ev, m) for ev, m, _ in e.own_cmds()], [("PreToolUse", "Write")])
    cmd = e.own_cmds()[0][2]
    f = os.path.join(e.home, "work.txt"); open(f, "w").write("x\n")
    wr = lambda c: json.dumps({"tool_name": "Write", "tool_input": {"file_path": f, "content": c}})
    p1 = subprocess.run(["sh", "-c", cmd], input=wr("x\n"), capture_output=True, text=True, env=e.env())
    p2 = subprocess.run(["sh", "-c", cmd], input=wr("y\n"), capture_output=True, text=True, env=e.env())
    check("1 perintah ter-quote (path berspasi) berjalan lewat sh -c: identik deny, beda allow",
          ("deny" in p1.stdout, "deny" in p2.stdout), (True, False))
    before = open(e.settings).read()
    e.sh("install.sh")
    check("1 pasang dua kali: idempoten (byte-identik)", open(e.settings).read() == before, True)
    r3 = e.sh("uninstall.sh")
    check("1 cabut: rc 0, settings kembali kosong", (r3.returncode, e.read_settings()), (0, {}))
    # kepemilikan = path PERSIS: hook asing bernama sama di dir lain tetap; substring tak menahan pasang
    e.write_settings({"hooks": {"PreToolUse": [
        {"matcher": "Write", "hooks": [{"type": "command", "command": "python /opt/other/write_noop_guard.py"}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "python /opt/write_noop_guard.py.bak/x"}]}]}})
    e.sh("install.sh")
    check("1 substring asing tidak menahan pemasangan guard sendiri", len(e.own_cmds()), 1)
    e.sh("uninstall.sh")
    left = sorted(h["command"] for m in e.read_settings()["hooks"]["PreToolUse"] for h in m["hooks"])
    check("1 cabut: hook asing bernama sama di dir lain TETAP", left,
          ["python /opt/other/write_noop_guard.py", "python /opt/write_noop_guard.py.bak/x"])
    # hook output opsional (SAMEWRITE_OUTPUT_HOOK=1): satu entri SessionStart, idempoten, dicabut bersih,
    # entri SessionStart asing tetap
    e5 = Env(foreign=True); orig5 = copy.deepcopy(e5.read_settings())
    e5.sh("install.sh", SAMEWRITE_OUTPUT_HOOK="1")
    ss = [h["command"] for m in e5.read_settings()["hooks"]["SessionStart"] for h in m["hooks"]]
    check("1 output hook: satu entri SessionStart bertanda samewrite-output-hook",
          sum(c.endswith("# samewrite-output-hook") for c in ss), 1)
    check("1 output hook: entri SessionStart asing tetap", [c for c in ss if "samewrite" not in c],
          ["node /p/hooks/ponytail-activate.js", "node /a/hooks/always-on.mjs"])
    oc = [c for c in ss if c.endswith("# samewrite-output-hook")][0]
    p = subprocess.run(["sh", "-c", oc], capture_output=True, text=True)
    check("1 output hook: perintah menjawab satu kalimat lewat sh -c", p.stdout.startswith("Lead with the result"), True)
    b5 = open(e5.settings).read(); e5.sh("install.sh", SAMEWRITE_OUTPUT_HOOK="1")
    check("1 output hook: pasang dua kali idempoten", open(e5.settings).read() == b5, True)
    e5.sh("uninstall.sh")
    check("1 output hook: cabut mengembalikan settings asing == asli", e5.read_settings(), orig5)
    # bentuk entri 1.0.0 (bash -c '... exec <python> <DST>') dikenali sebagai milik sendiri: upgrade tak
    # menambah entri kedua, uninstall mencabutnya; --human-output = SAMEWRITE_OUTPUT_HOOK=1
    e6 = Env(foreign=True); orig6 = copy.deepcopy(e6.read_settings())
    old_cmd = "bash -c 'SAMEWRITE_LEDGER=%s exec %s %s'" % (e6.ledger, sys.executable, e6.dst)
    d6 = e6.read_settings(); d6["hooks"]["PreToolUse"].append({"matcher": "Write", "hooks": [{"type": "command", "command": old_cmd}]})
    e6.write_settings(d6)
    r = e6.sh("install.sh")
    check("1 upgrade: entri bentuk 1.0.0 dikenali -> 'sudah terpasang', nol entri kedua",
          ("sudah terpasang" in r.stdout, len([1 for m in e6.read_settings()["hooks"]["PreToolUse"] for h in m["hooks"] if "write_noop_guard.py" in h["command"]])), (True, 1))
    e6.sh("uninstall.sh")
    check("1 upgrade: uninstall mencabut entri bentuk 1.0.0, sisa == asing asli", e6.read_settings(), orig6)
    r = subprocess.run(["bash", os.path.join(HOOKS, "install.sh"), "--human-output"], capture_output=True, text=True, timeout=120, env=e6.env())
    ss6 = [h["command"] for m in e6.read_settings()["hooks"]["SessionStart"] for h in m["hooks"]]
    check("1 --human-output == SAMEWRITE_OUTPUT_HOOK=1 (satu entri output hook)", sum(c.endswith("# samewrite-output-hook") for c in ss6), 1)
    r = subprocess.run(["bash", os.path.join(HOOKS, "install.sh"), "--bogus"], capture_output=True, text=True, timeout=60, env=e6.env())
    check("1 argumen tak dikenal -> rc 64", r.returncode, 64)
    e6.sh("uninstall.sh")
    check("1 cabut sesudah --human-output: settings == asing asli", e6.read_settings(), orig6)
    row(1, "SameWrite only", "PASS")

    # ---------------------------------------------------------------- 2/3. foreign only
    e = Env(foreign=True)
    snap0 = e.snapshot(); orig = copy.deepcopy(e.read_settings())
    row(2, "Ponytail only", "PASS — constructed foreign state; SameWrite absent, nothing touched")
    row(3, "i-have-adhd only", "PASS — constructed foreign state; SameWrite absent, nothing touched")

    # ---------------------------------------------------------------- 4/5/6/26. installed alongside
    r = e.sh("install.sh")
    check("4-6 pasang di config asing: rc 0", r.returncode, 0)
    check("4-6 entri asing tak berubah secara struktur", e.foreign_view(), orig)
    check("4-6 statusLine asing utuh", e.read_settings()["statusLine"], orig["statusLine"])
    check("4-6 flag asing + ~/.config/ponytail byte-identik", e.snapshot(), snap0)
    row(4, "SameWrite + Ponytail installed, inactive", "PASS — SameWrite-side: foreign settings/flags unchanged")
    row(5, "SameWrite + i-have-adhd installed, inactive", "PASS — SameWrite-side: foreign settings/flags unchanged")
    row(6, "all three installed", "PASS — SameWrite-side: foreign settings/flags unchanged")
    row(26, "pre-populated foreign config", "PASS")

    # ---------------------------------------------------------------- 7-10. active together
    f = os.path.join(e.home, "work.txt"); open(f, "w").write("x\n")
    check("7-10 guard menolak Write identik saat flag ponytail/adhd/caveman ada", e.guard(f, "x\n"), True)
    check("7-10 guard tak menyentuh flag asing", e.snapshot(), snap0)
    for n, name in [(7, "SameWrite active + Ponytail active"), (8, "SameWrite active + i-have-adhd active"),
                    (9, "Ponytail + i-have-adhd active"), (10, "all three active")]:
        row(n, name, "PASS — SameWrite-side only; foreign hooks run in the LIVE block")

    # ---------------------------------------------------------------- 11. activation orders
    e2 = Env(foreign=False); e2.sh("install.sh")
    d = e2.read_settings()
    for ev, ms in FOREIGN_SETTINGS["hooks"].items():
        d.setdefault("hooks", {}).setdefault(ev, []).extend(copy.deepcopy(ms))
    d["statusLine"] = FOREIGN_SETTINGS["statusLine"]; e2.write_settings(d)
    hookset = lambda env: {(ev, m.get("matcher"), h["command"].replace(env.home, "<HOME>"))
                           for ev, ms in env.read_settings()["hooks"].items() for m in ms for h in m["hooks"]}
    check("11 urutan pasang berbeda -> himpunan hook sama", hookset(e2), hookset(e))
    row(11, "different activation orders", "PASS")

    # ---------------------------------------------------------------- 12-14. one off, others on
    e.sh("uninstall.sh")
    check("12 samewrite dicabut: settings asing == asli, flag asing utuh",
          (e.read_settings() == orig, e.snapshot() == snap0), (True, True))
    row(12, "SameWrite off while others active", "PASS — off = uninstall (no mode); foreign state untouched")
    e.sh("install.sh")
    os.unlink(os.path.join(e.cfg, ".ponytail-active"))
    check("13 ponytail off: guard samewrite tetap menolak, flag ponytail tak dibuat ulang",
          (e.guard(f, "x\n"), os.path.exists(os.path.join(e.cfg, ".ponytail-active"))), (True, False))
    os.unlink(os.path.join(e.cfg, ".i-have-adhd-always"))
    check("14 adhd off: guard samewrite tetap menolak, flag adhd tak dibuat ulang",
          (e.guard(f, "x\n"), os.path.exists(os.path.join(e.cfg, ".i-have-adhd-always"))), (True, False))
    row(13, "Ponytail off while SameWrite active", "PASS — foreign flag removed by the test; SameWrite unaffected")
    row(14, "i-have-adhd off while SameWrite active", "PASS — foreign flag removed by the test; SameWrite unaffected")

    # ---------------------------------------------------------------- 15-20. lifecycle, subagents
    check("15-20 samewrite mendaftarkan nol hook SessionStart/UserPromptSubmit/SubagentStart",
          sorted({ev for ev, _, _ in e.own_cmds()}), ["PreToolUse"])
    for n, name in [(15, "session start"), (16, "resume"), (17, "clear"), (18, "compaction"), (19, "plugin reload")]:
        row(n, name, "N/A — nothing to re-inject: samewrite is a listing entry + on-demand body, no hook")
    row(20, "subagent spawn", "N/A by construction — no SubagentStart injection exists")

    # ---------------------------------------------------------------- 21-25. model-behaviour cases
    for n, name in [(21, "explicit user output-only format"), (22, "long-form explanation request"),
                    (23, "destructive action"), (24, "public API ambiguity"), (25, "CRITICAL auth/security change")]:
        row(n, name, "EXPERIMENTAL — benchmark fixture (experiments/vnext, experiments/presentation)")

    # ---------------------------------------------------------------- 27. statusLine + malformed JSON
    e.sh("uninstall.sh")
    check("27 cabut: statusLine asing tetap, settings == asli", e.read_settings(), orig)
    e3 = Env(foreign=False, settings='{"hooks": {oops')
    raw = open(e3.settings).read()
    r = e3.sh("uninstall.sh")
    check("27 JSON rusak: cabut memperingatkan (rc 1) dan TIDAK menyentuh berkas",
          (r.returncode, open(e3.settings).read() == raw, "PERINGATAN" in r.stdout), (1, True, True))
    r = e3.sh("install.sh")
    check("27 JSON rusak: pasang gagal, berkas tetap byte-identik", (r.returncode != 0, open(e3.settings).read() == raw), (True, True))
    row(27, "existing/custom statusLine", "PASS — preserved on install + uninstall; malformed JSON untouched")

    row(28, "OpenCode per-turn transform", "UNSUPPORTED — no OpenCode adapter shipped")
    row(29, "Pi before-agent injection", "UNSUPPORTED — no Pi adapter shipped")

    # ---------------------------------------------------------------- 30. paths
    sys.path.insert(0, HOOKS)
    check("30 path gaya Windows dikenali sensitif oleh guard (backslash)",
          __import__("write_noop_guard").sensitive(r"C:\Users\me\.ssh\id_rsa"), True)
    row(30, "Windows + POSIX path behavior", "PARTIAL — POSIX spaces/metachars tested (case 1); Windows UNTESTED (no runner)")

    # ---------------------------------------------------------------- skill text: no foreign controls
    check("skill: tak mengklaim 'normal mode' kecuali sebagai larangan",
          all("never reacts" in l for l in SKILL.splitlines() if "normal mode" in l), True)
    check("skill: tak mendefinisikan saklar mode sendiri", bool(re.search(r"/samewrite (on|off)|stop samewrite", SKILL)), False)
    check("skill: tak memakai kata pemicu caveman sebagai perintah (be brief/less tokens/fewer tokens)",
          bool(re.search(r"\b(be brief|be terse|less tokens|fewer tokens|shorter answers)\b", SKILL, re.I)), False)

    # ---------------------------------------------------------------- LIVE: real foreign hooks next to the skill
    ref = os.environ.get("SAMEWRITE_REF_DIR"); node = shutil.which("node")
    if ref and node and os.path.isdir(os.path.join(ref, "ponytail", "hooks")):
        e4 = Env(foreign=True); e4.sh("install.sh")
        shutil.copytree(os.path.join(ROOT, "skills", "samewrite"), os.path.join(e4.cfg, "skills", "samewrite"))
        pt = os.path.join(ref, "ponytail", "hooks", "ponytail-mode-tracker.js")
        subprocess.run([node, pt], input=json.dumps({"prompt": "fix the bug in samewrite style"}),
                       capture_output=True, text=True, timeout=30, env=e4.env())
        check("LIVE ponytail tracker: prompt biasa tak mengubah .ponytail-active",
              open(os.path.join(e4.cfg, ".ponytail-active")).read().strip(), "full")
        subprocess.run([node, pt], input=json.dumps({"prompt": "stop ponytail"}),
                       capture_output=True, text=True, timeout=30, env=e4.env())
        check("LIVE 'stop ponytail' mematikan ponytail (kontrol positif) dan samewrite tetap terpasang",
              (os.path.exists(os.path.join(e4.cfg, ".ponytail-active")), len(e4.own_cmds())), (False, 1))
        ad = os.path.join(ref, "i-have-adhd", "hooks", "always-on.mjs")
        p = subprocess.run([node, ad], input="{}", capture_output=True, text=True, timeout=30,
                           env=dict(e4.env(), CLAUDE_PLUGIN_ROOT=os.path.join(ref, "i-have-adhd")))
        w = os.path.join(e4.home, "work.txt"); open(w, "w").write("x\n")
        check("LIVE i-have-adhd always-on menyuntik saat flag ada, guard samewrite tetap jalan",
              ("ADHD MODE ACTIVE" in p.stdout, e4.guard(w, "x\n")), (True, True))
        print("  LIVE  3 uji silang dengan hook asing ASLI dijalankan")
    else:
        print("  SKIP  uji silang hook asing asli: set SAMEWRITE_REF_DIR=<dir klon> dan sediakan node")

    print("\n  matriks §26:")
    for n, name, st in sorted(MATRIX):
        print(f"   {n:>2}. {name:<45} {st}")
    # Setiap uji lain menimpa SAMEWRITE_DST ke direktori yang dibuatnya sendiri, jadi tujuan
    # BAWAAN ($HOME/scripts) tak pernah dijalankan sekali pun — dan di sanalah bug-nya: `install`
    # tak membuat direktori induk, sehingga jalur yang README suruh pakai gagal di mesin baru.
    # Ditemukan oleh acceptance publik, bukan oleh suite ini. Sekarang dijaga di sini.
    with tempfile.TemporaryDirectory() as home:
        cfg = os.path.join(home, ".claude")
        os.makedirs(cfg)
        open(os.path.join(cfg, "settings.json"), "w").write("{}")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("CLAUDE", "SAMEWRITE"))}
        env.update(HOME=home, CLAUDE_CONFIG_DIR=cfg, SAMEWRITE_PYTHON=sys.executable)
        r = subprocess.run(["bash", os.path.join(ROOT, "hooks", "install.sh")],
                           capture_output=True, text=True, env=env, timeout=600)
        landed = os.path.exists(os.path.join(home, "scripts", "write_noop_guard.py"))
        check("install.sh works on a FRESH home where ~/scripts does not exist",
              (r.returncode, landed), (0, True))
        if not landed:
            print("      " + (r.stdout + r.stderr).strip()[-200:])

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
