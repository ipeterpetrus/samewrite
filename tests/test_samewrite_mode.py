#!/usr/bin/env python3
"""Uji hooks/samewrite_mode.py + integrasinya dengan write_noop_guard.py. Berdiri sendiri.

Yang dijaga: saklar hanya menjawab frasa MILIK samewrite (whole-message), tak pernah
menjawab `normal mode` / `stop ponytail` / `stop caveman` / `stop adhd mode`; satu-satunya
berkas state = <state dir>/samewrite-disabled; guard dan saklar membaca dir yang SAMA;
fail-open pada stdin rusak; versi hook = versi plugin."""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODE = os.path.join(ROOT, "hooks", "samewrite_mode.py")
GUARD = os.path.join(ROOT, "hooks", "write_noop_guard.py")
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import samewrite_mode as sm  # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


def run(script, args, payload, env):
    e = dict(os.environ)
    e.pop("SAMEWRITE_CORE", None); e.pop("SAMEWRITE_ALLOW_NOOP", None)
    e.update(env)
    p = subprocess.run([sys.executable, script] + args, input=payload, capture_output=True,
                       text=True, timeout=20, env=e)
    return p.returncode, p.stdout


def hook(args, prompt, env, raw=None):
    payload = raw if raw is not None else json.dumps({"prompt": prompt, "session_id": "s1"})
    return run(MODE, args, payload, env)


def main():
    # --- parser: frasa sendiri, whole-message, tanda baca/kapital/spasi diabaikan
    for p, want in [("stop samewrite", "off"), ("Stop SameWrite!", "off"), ("samewrite off.", "off"),
                    ("  samewrite   on ", "on"), ("enable samewrite", "on"),
                    ("samewrite status", "status"), ("samewrite", "status"),
                    ("/samewrite", "status"), ("/samewrite off", "off"), ("/samewrite on", "on"),
                    ("/samewrite:samewrite off", "off"), ("/samewrite stop", "off")]:
        check(f"parse {p!r}", sm.parse(p), want)
    # --- frasa milik plugin lain / kalimat tugas: TIDAK bereaksi (§7 master prompt)
    for p in ["normal mode", "Normal mode.", "stop ponytail", "stop caveman", "stop adhd mode",
              "/ponytail off", "/caveman off", "/i-have-adhd", "be brief", "less tokens",
              "add a stop samewrite button to the settings page",
              "explain what samewrite off would do", "samewrite off and then run the tests",
              "/samewrite-review", "/samewriter off", "", None]:
        check(f"abaikan {p!r}", sm.parse(p), None)

    with tempfile.TemporaryDirectory() as d:
        env = {"SAMEWRITE_STATE_DIR": d, "SAMEWRITE_ROOT": d}   # ROOT: guard hanya menilai berkas di pohon ini
        marker = os.path.join(d, "samewrite-disabled")

        rc, out = hook(["prompt"], "add caching to fetch()", env)
        check("prompt biasa: exit 0, nol keluaran", (rc, out), (0, ""))
        rc, out = hook(["prompt"], "normal mode", env)
        check("'normal mode': nol keluaran, nol marker", (rc, out, os.path.exists(marker)), (0, "", False))

        rc, out = hook(["prompt"], "stop samewrite", env)
        j = json.loads(out)
        check("stop samewrite -> marker dibuat", os.path.exists(marker), True)
        check("stop samewrite -> additionalContext bernama-ruang",
              j["hookSpecificOutput"]["additionalContext"].startswith("SAMEWRITE OFF"), True)
        check("hookEventName benar", j["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        check("marker 0600", oct(os.stat(marker).st_mode & 0o777), "0o600")
        check("marker tak menyebut plugin lain", os.listdir(d), ["samewrite-disabled"])

        rc, out = hook(["prompt"], "samewrite status", env)
        check("status saat off", "SAMEWRITE status: off" in out, True)

        # guard menghormati marker: Write identik LOLOS saat samewrite off. Kontrol positif dulu:
        # tanpa marker guard MENOLAK — kalau tidak, "lolos saat off" cuma kebetulan.
        f = os.path.join(d, "x.txt"); open(f, "w").write("same\n")
        wr = json.dumps({"tool_name": "Write", "tool_input": {"file_path": f, "content": "same\n"}})
        os.unlink(marker)
        check("kontrol positif: guard MENOLAK identik saat on", "deny" in run(GUARD, [], wr, env)[1], True)
        hook(["prompt"], "stop samewrite", env)
        rc, out = run(GUARD, [], wr, env)
        check("guard: identik DILOLOSKAN saat samewrite off", "deny" in out, False)

        rc, out = hook(["prompt"], "samewrite on", env)
        check("samewrite on -> marker hilang", os.path.exists(marker), False)
        check("samewrite on -> inti disuntik sekali", out.count("samewrite:"), 1)
        rc, out = run(GUARD, [], json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": f, "content": "same\n"}}), env)
        check("guard: identik DITOLAK lagi saat samewrite on", "deny" in out, True)

        # idempoten: dua kali off tetap satu marker, dua kali on tetap tak ada
        hook(["prompt"], "samewrite off", env); hook(["prompt"], "samewrite off", env)
        check("off dua kali: satu marker", os.listdir(d).count("samewrite-disabled"), 1)
        hook(["prompt"], "samewrite on", env); hook(["prompt"], "samewrite on", env)
        check("on dua kali: bersih", os.path.exists(marker), False)

        # SessionStart: inti hanya bila SAMEWRITE_CORE=1 dan tidak sedang off
        rc, out = hook(["session"], "", env)
        check("session tanpa SAMEWRITE_CORE: senyap", out, "")
        rc, out = hook(["session"], "", dict(env, SAMEWRITE_CORE="1"))
        check("session dengan SAMEWRITE_CORE=1: satu baris inti", out.strip(), sm.CORE)
        check("inti tetap kecil (<= 400 karakter)", len(sm.CORE) <= 400, True)
        hook(["prompt"], "stop samewrite", env)
        rc, out = hook(["session"], "", dict(env, SAMEWRITE_CORE="1"))
        check("session saat off: senyap walau SAMEWRITE_CORE=1", out, "")
        hook(["prompt"], "samewrite on", env)

        # fail-open
        rc, out = hook(["prompt"], "", env, raw="{bukan json")
        check("stdin rusak: exit 0, senyap", (rc, out), (0, ""))
        rc, out = hook(["prompt"], "", env, raw="[1,2]")
        check("stdin bukan objek: exit 0, senyap", (rc, out), (0, ""))
        rc, out = hook(["bogus"], "stop samewrite", env)
        check("subperintah asing: senyap, marker tak dibuat", (rc, out, os.path.exists(marker)),
              (0, "", False))
        ro = os.path.join(d, "ro"); os.makedirs(ro); os.chmod(ro, 0o500)
        rc, out = hook(["prompt"], "stop samewrite", {"SAMEWRITE_STATE_DIR": os.path.join(ro, "sub")})
        check("state dir tak bisa ditulis: exit 0 (fail-open)", rc, 0)
        os.chmod(ro, 0o700)

        # guard dan saklar menyelesaikan dir state dengan urutan yang sama
        for e in ({"SAMEWRITE_STATE_DIR": d, "CLAUDE_CONFIG_DIR": "/nope", "SAMEWRITE_ROOT": d},
                  {"CLAUDE_CONFIG_DIR": d, "SAMEWRITE_ROOT": d}):
            hook(["prompt"], "stop samewrite", e)
            rc, out = run(GUARD, [], json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": f, "content": "same\n"}}), e)
            check(f"guard mengikuti saklar via {sorted(e)}", "deny" in out, False)
            hook(["prompt"], "samewrite on", e)

    pj = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    check("versi hook = versi plugin.json", sm.VERSION, pj["version"])

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
