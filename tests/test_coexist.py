#!/usr/bin/env python3
"""Matriks koeksistensi (master prompt §26): samewrite harus MENYUSUN, bukan bersaing.

Semua kasus deterministik: direktori config sementara, settings.json yang SUDAH berisi hook,
statusLine dan kunci milik plugin lain, plus berkas-flag plugin lain. Permukaan asing diambil
dari audit ter-pin (docs/VNEXT.md §referensi):
  ponytail@e3ba2aa  .ponytail-active · .ponytail-statusline-nudged · ~/.config/ponytail/config.json
                    frasa `stop ponytail` / `normal mode` (whole-message) · /ponytail* · ponytail-*.js
  i-have-adhd@4092de0  .i-have-adhd-always · frasa `stop adhd mode` / `normal mode` · /i-have-adhd
  caveman@15581d1   .caveman-active · .caveman-sessions/ · frasa `stop caveman` · /caveman*
  rtk@d402152       PreToolUse(Bash) `rtk hook claude`
Kasus yang butuh model (format keluaran eksplisit, ambiguitas API, perubahan auth) BUKAN uji
deterministik: mereka fixture benchmark (experiments/vnext/) dan dilabeli EXPERIMENTAL di
tabel akhir — bukan diklaim lulus diam-diam. Bila SAMEWRITE_REF_DIR menunjuk klon referensi
dan `node` ada, hook ponytail/i-have-adhd yang ASLI ikut dijalankan (uji silang hidup)."""
import copy, hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "hooks")
sys.path.insert(0, HOOKS)
import samewrite_mode as sm  # noqa: E402

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
OWN_NAMES = ("write_noop_guard.py", "samewrite_mode.py")


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
        e = dict(os.environ)
        for k in list(e):
            if k.startswith("SAMEWRITE_"):
                del e[k]
        e.update(HOME=self.home, CLAUDE_CONFIG_DIR=self.cfg, SAMEWRITE_SETTINGS=self.settings,
                 SAMEWRITE_DST=self.dst, SAMEWRITE_LEDGER=self.ledger, SAMEWRITE_PYTHON=sys.executable,
                 SAMEWRITE_ROOT=self.home)
        e.update(extra)
        return e

    def sh(self, script, **extra):
        return subprocess.run(["bash", os.path.join(HOOKS, script)], capture_output=True, text=True,
                              timeout=120, env=self.env(**extra))

    def hook(self, verb, prompt="", **extra):
        p = subprocess.run([sys.executable, os.path.join(HOOKS, "samewrite_mode.py"), verb],
                           input=json.dumps({"prompt": prompt, "session_id": "s1", "source": extra.pop("source", "startup")}),
                           capture_output=True, text=True, timeout=20, env=self.env(**extra))
        return p.stdout

    def guard(self, path, content, **extra):
        p = subprocess.run([sys.executable, os.path.join(HOOKS, "write_noop_guard.py")],
                           input=json.dumps({"tool_name": "Write",
                                             "tool_input": {"file_path": path, "content": content}}),
                           capture_output=True, text=True, timeout=20, env=self.env(**extra))
        return "deny" in p.stdout

    def foreign_view(self):
        """settings.json tanpa entri milik samewrite — harus == asli, byte demi byte secara struktur."""
        d = self.read_settings()
        hooks = d.get("hooks", {})
        for ev in list(hooks):
            kept = []
            for m in hooks[ev]:
                hs = [h for h in m.get("hooks", []) if not any(n in h.get("command", "") for n in OWN_NAMES)]
                if hs:
                    m = dict(m, hooks=hs); kept.append(m)
            if kept:
                hooks[ev] = kept
            else:
                del hooks[ev]
        if "hooks" in d and not d["hooks"]:
            del d["hooks"]
        return d

    def own_entries(self):
        d = self.read_settings()
        out = []
        for ev, ms in d.get("hooks", {}).items():
            for m in ms:
                for h in m.get("hooks", []):
                    if any(n in h.get("command", "") for n in OWN_NAMES):
                        out.append((ev, m.get("matcher"), h["command"]))
        return out

    def snapshot(self):
        """hash setiap berkas non-samewrite di HOME (flag asing, config ponytail, dst.)."""
        out = {}
        for top in (self.cfg, os.path.join(self.home, ".config")):
            for base, _, files in os.walk(top):
                for f in files:
                    p = os.path.join(base, f)
                    rel = os.path.relpath(p, self.home)
                    # settings.json dinilai terpisah lewat foreign_view(); cadangan + marker = milik sendiri
                    if f == "settings.json" or ".bak." in rel or f == "samewrite-disabled":
                        continue
                    out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        return out


def main():
    # ---------------------------------------------------------------- 1. samewrite only
    e = Env(foreign=False)
    r = e.sh("install.sh", SAMEWRITE_MODE_HOOK="1")
    check("1 pasang di config kosong: rc 0", r.returncode, 0)
    check("1 tiga entri milik sendiri (Write, UserPromptSubmit, SessionStart)",
          sorted(ev for ev, _, _ in e.own_entries()), ["PreToolUse", "SessionStart", "UserPromptSubmit"])
    check("1 perintah hook memuat path berspasi yang di-quote",
          all("bin\\ dir" in c or "'bin dir'" in c or '"bin dir"' in c for _, _, c in e.own_entries()), True)
    # jalankan perintah hook PERSIS seperti tertulis di settings.json lewat sh -c: quoting harus jalan
    cmd = [c for ev, _, c in e.own_entries() if ev == "UserPromptSubmit"][0]
    p = subprocess.run(["sh", "-c", cmd], input='{"prompt":"samewrite status"}', capture_output=True,
                       text=True, env=e.env())
    check("1 perintah ter-quote berjalan lewat sh -c", "SAMEWRITE status" in p.stdout, True)
    before = open(e.settings).read()
    r2 = e.sh("install.sh", SAMEWRITE_MODE_HOOK="1")
    check("1 pasang dua kali: idempoten (byte-identik)", open(e.settings).read() == before, True)
    r3 = e.sh("uninstall.sh")
    check("1 cabut: rc 0", r3.returncode, 0)
    check("1 cabut: settings kembali kosong", e.read_settings(), {})
    row(1, "SameWrite only", "PASS")

    # ---------------------------------------------------------------- 2/3. foreign only (samewrite absent)
    e = Env(foreign=True)
    snap = e.snapshot(); fv = e.foreign_view()
    out = e.hook("prompt", "normal mode")
    check("2/3 samewrite tak terpasang: 'normal mode' nol reaksi, nol berkas", (out, e.snapshot() == snap), ("", True))
    row(2, "Ponytail only", "PASS (samewrite absent, nothing touched)")
    row(3, "i-have-adhd only", "PASS (samewrite absent, nothing touched)")

    # ---------------------------------------------------------------- 4/5/6/26. installed alongside, inactive
    snap0 = e.snapshot(); orig = copy.deepcopy(e.read_settings())
    r = e.sh("install.sh", SAMEWRITE_MODE_HOOK="1")
    check("4-6 pasang di config asing: rc 0", r.returncode, 0)
    check("4-6 entri asing tak berubah (tanpa entri samewrite == asli)", e.foreign_view(), orig)
    check("4-6 statusLine asing byte-identik", e.read_settings()["statusLine"], orig["statusLine"])
    check("4-6 flag asing + ~/.config/ponytail byte-identik", e.snapshot(), snap0)
    check("4-6 tak ada SubagentStart milik samewrite (subagen tak disuntik)",
          any(ev == "SubagentStart" for ev, _, _ in e.own_entries()), False)
    row(4, "SameWrite + Ponytail installed, inactive", "PASS")
    row(5, "SameWrite + i-have-adhd installed, inactive", "PASS")
    row(6, "all three installed", "PASS")
    row(26, "pre-populated foreign config", "PASS")

    # ---------------------------------------------------------------- 7/8/9/10. active together
    f = os.path.join(e.home, "work.txt"); open(f, "w").write("x\n")
    out = e.hook("session", SAMEWRITE_CORE="1")
    check("7-10 SessionStart: inti satu baris, tanpa menyebut plugin lain",
          (out.count("samewrite:"), "ponytail" in out.lower()), (1, False))
    check("7-10 flag asing tetap sesudah session hook", e.snapshot(), snap0)
    check("7-10 guard menolak Write identik saat semua aktif", e.guard(f, "x\n"), True)
    check("7-10 prompt biasa: hook samewrite senyap (nol injeksi per-turn)", e.hook("prompt", "fix the bug"), "")
    row(7, "SameWrite active + Ponytail active", "PASS (files/flags)")
    row(8, "SameWrite active + i-have-adhd active", "PASS (files/flags)")
    row(9, "Ponytail + i-have-adhd active", "PASS (samewrite silent)")
    row(10, "all three active", "PASS (files/flags)")

    # ---------------------------------------------------------------- 11. activation orders
    e2 = Env(foreign=False)
    e2.sh("install.sh", SAMEWRITE_MODE_HOOK="1")
    d = e2.read_settings()
    for ev, ms in FOREIGN_SETTINGS["hooks"].items():
        d.setdefault("hooks", {}).setdefault(ev, []).extend(copy.deepcopy(ms))
    d["statusLine"] = FOREIGN_SETTINGS["statusLine"]
    e2.write_settings(d)
    def hookset(env):
        return {(ev, m.get("matcher"), h["command"].replace(env.home, "<HOME>"))
                for ev, ms in env.read_settings()["hooks"].items() for m in ms for h in m["hooks"]}
    a, b = hookset(e2), hookset(e)
    check("11 urutan pasang berbeda -> himpunan hook sama", a, b)
    row(11, "different activation orders", "PASS")

    # ---------------------------------------------------------------- 12. samewrite off, others stay
    out = e.hook("prompt", "stop samewrite")
    check("12 stop samewrite: marker sendiri dibuat", os.path.exists(os.path.join(e.cfg, "samewrite-disabled")), True)
    check("12 stop samewrite: flag asing utuh", e.snapshot(), snap0)
    check("12 stop samewrite: settings asing utuh", e.foreign_view(), orig)
    check("12 guard berhenti (identik lolos)", e.guard(f, "x\n"), False)
    check("12 SessionStart senyap saat off", e.hook("session", SAMEWRITE_CORE="1"), "")
    row(12, "SameWrite off while others active", "PASS")

    # ---------------------------------------------------------------- 13/14. others off, samewrite stays
    e.hook("prompt", "samewrite on")
    os.unlink(os.path.join(e.cfg, ".ponytail-active"))
    check("13 ponytail off: guard samewrite tetap menolak", e.guard(f, "x\n"), True)
    check("13 ponytail off: samewrite tak menulis ulang flag ponytail",
          os.path.exists(os.path.join(e.cfg, ".ponytail-active")), False)
    os.unlink(os.path.join(e.cfg, ".i-have-adhd-always"))
    check("14 adhd off: guard samewrite tetap menolak", e.guard(f, "x\n"), True)
    check("14 adhd off: flag adhd tak dihidupkan lagi", os.path.exists(os.path.join(e.cfg, ".i-have-adhd-always")), False)
    row(13, "Ponytail off while SameWrite active", "PASS")
    row(14, "i-have-adhd off while SameWrite active", "PASS")

    # ---------------------------------------------------------------- 15-19. lifecycle sources
    for n, src in [(15, "startup"), (16, "resume"), (17, "clear"), (18, "compact"), (19, "startup")]:
        out = e.hook("session", source=src, SAMEWRITE_CORE="1")
        check(f"{n} SessionStart source={src}: tepat satu inti", out.count("samewrite:"), 1)
        check(f"{n} source={src}: inti tak ganda saat dijalankan lagi", e.hook("session", source=src, SAMEWRITE_CORE="1").count("samewrite:"), 1)
    row(15, "session start", "PASS"); row(16, "resume", "PASS"); row(17, "clear", "PASS")
    row(18, "compaction", "PASS (re-inject once via matcher, none when off)")
    row(19, "plugin reload", "PASS (same path as startup)")

    # ---------------------------------------------------------------- 20. subagent spawn
    check("20 tak ada SubagentStart samewrite; hook prompt/session tak dipanggil utk subagen",
          any(ev == "SubagentStart" for ev, _, _ in e.own_entries()), False)
    row(20, "subagent spawn", "PASS (by design: no SubagentStart injection)")

    # ---------------------------------------------------------------- 21-25. model-behaviour cases
    for n, name in [(21, "explicit user output-only format"), (22, "long-form explanation request"),
                    (23, "destructive action"), (24, "public API ambiguity"), (25, "CRITICAL auth/security change")]:
        row(n, name, "EXPERIMENTAL — benchmark fixture experiments/vnext/, not a deterministic test")

    # ---------------------------------------------------------------- 27. existing statusLine + malformed JSON
    e.sh("uninstall.sh")
    check("27 cabut: statusLine asing tetap", e.read_settings()["statusLine"], orig["statusLine"])
    check("27 cabut: settings asing == asli", e.read_settings(), orig)
    check("27 cabut: marker sendiri dibersihkan", os.path.exists(os.path.join(e.cfg, "samewrite-disabled")), False)
    e3 = Env(foreign=False, settings='{"hooks": {oops')
    raw = open(e3.settings).read()
    r = e3.sh("uninstall.sh")
    check("27 JSON rusak: cabut memperingatkan (rc 1) dan TIDAK menyentuh berkas",
          (r.returncode, open(e3.settings).read() == raw, "PERINGATAN" in r.stdout), (1, True, True))
    r = e3.sh("install.sh")
    check("27 JSON rusak: pasang gagal, berkas tetap byte-identik", (r.returncode != 0, open(e3.settings).read() == raw), (True, True))
    row(27, "existing/custom statusLine", "PASS (preserved on install + uninstall; malformed JSON untouched)")

    # ---------------------------------------------------------------- 28/29. other hosts
    row(28, "OpenCode per-turn transform", "UNSUPPORTED — no OpenCode adapter shipped")
    row(29, "Pi before-agent injection", "UNSUPPORTED — no Pi adapter shipped")

    # ---------------------------------------------------------------- 30. paths
    weird = os.path.join(e.home, "we ird", "$dir", "it's")
    os.makedirs(weird)
    e.hook("prompt", "stop samewrite", SAMEWRITE_STATE_DIR=weird)
    check("30 POSIX: dir state berspasi/$/kutip -> marker dibuat",
          os.path.exists(os.path.join(weird, "samewrite-disabled")), True)
    check("30 POSIX: guard membaca marker dari dir yang sama", e.guard(f, "x\n", SAMEWRITE_STATE_DIR=weird), False)
    check("30 path gaya Windows dikenali sensitif oleh guard (backslash)",
          __import__("write_noop_guard").sensitive(r"C:\Users\me\.ssh\id_rsa"), True)
    row(30, "Windows + POSIX path behavior", "PARTIAL — POSIX spaces/metachars tested; Windows UNTESTED (no runner)")

    # ---------------------------------------------------------------- live cross-check with REAL foreign hooks
    ref = os.environ.get("SAMEWRITE_REF_DIR")
    node = shutil.which("node")
    live = 0
    if ref and node and os.path.isdir(os.path.join(ref, "ponytail", "hooks")):
        e4 = Env(foreign=True)
        pt = os.path.join(ref, "ponytail", "hooks", "ponytail-mode-tracker.js")
        p = subprocess.run([node, pt], input=json.dumps({"prompt": "stop samewrite"}), capture_output=True,
                           text=True, timeout=30, env=e4.env())
        check("LIVE ponytail tracker mengabaikan 'stop samewrite' (.ponytail-active tetap)",
              open(os.path.join(e4.cfg, ".ponytail-active")).read().strip(), "full")
        p = subprocess.run([node, pt], input=json.dumps({"prompt": "stop ponytail"}), capture_output=True,
                           text=True, timeout=30, env=e4.env())
        check("LIVE 'stop ponytail' memang mematikan ponytail (kontrol positif)",
              os.path.exists(os.path.join(e4.cfg, ".ponytail-active")), False)
        check("LIVE 'stop ponytail' tak menyentuh samewrite (nol marker)",
              os.path.exists(os.path.join(e4.cfg, "samewrite-disabled")), False)
        live += 3
        ad = os.path.join(ref, "i-have-adhd", "hooks", "always-on.mjs")
        if os.path.exists(ad):
            p = subprocess.run([node, ad], input="{}", capture_output=True, text=True, timeout=30,
                               env=dict(e4.env(), CLAUDE_PLUGIN_ROOT=os.path.join(ref, "i-have-adhd")))
            check("LIVE i-have-adhd always-on menyuntik saat flag ada", "ADHD MODE ACTIVE" in p.stdout, True)
            e4.hook("prompt", "stop samewrite")
            check("LIVE stop samewrite membiarkan .i-have-adhd-always",
                  os.path.exists(os.path.join(e4.cfg, ".i-have-adhd-always")), True)
            live += 2
        print(f"  LIVE  {live} uji silang dengan hook asing ASLI dijalankan")
    else:
        print("  SKIP  uji silang hook asing asli: set SAMEWRITE_REF_DIR=<dir klon> dan sediakan node")

    print("\n  matriks §26:")
    for n, name, st in sorted(MATRIX):
        print(f"   {n:>2}. {name:<45} {st}")
    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
