#!/usr/bin/env python3
"""Uji drift: adapters/ = hasil generate dari SKILL.md kanonik; permukaan perintah di README,
SKILL.md dan hook saling cocok; versi plugin/marketplace/hook satu angka. Berdiri sendiri."""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import adapters  # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


def main():
    skill = open(os.path.join(ROOT, "skills", "samewrite", "SKILL.md"), encoding="utf-8").read()
    fm, body = adapters.split(skill)

    # 1. adapter yang ter-commit = hasil generate (drift nol)
    r = subprocess.run([sys.executable, adapters.__file__, "--check"], capture_output=True, text=True)
    check("adapters --check hijau", r.returncode, 0)
    for name, text in adapters.render().items():
        check(f"{name}: badan byte-identik dengan SKILL.md", text.endswith(body), True)
        check(f"{name}: tak membawa front matter Claude", "name: samewrite" in text, False)

    # 2. --check benar-benar bisa MERAH: mutasi adapter di salinan, harap exit 1
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["cp", "-r", ROOT + "/.", d], check=True)
        p = os.path.join(d, "adapters", "AGENTS.samewrite.md")
        open(p, "a").write("\ndrift\n")
        r = subprocess.run([sys.executable, os.path.join(d, "tools", "adapters.py"), "--check"],
                           capture_output=True, text=True)
        check("adapter yang dimutasi -> --check exit 1", r.returncode, 1)
        check("pesan menyebut berkas yang menyimpang", "AGENTS.samewrite.md" in r.stdout, True)

    # 3. permukaan perintah: samewrite TIDAK punya saklar/mode — hanya nama skill-nya sendiri
    check("SKILL.md tak mendefinisikan /samewrite on|off atau 'stop samewrite'",
          bool(re.search(r"/samewrite (on|off|status)|stop samewrite", skill)), False)
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    check("frasa 'normal mode' hanya muncul sebagai larangan di SKILL.md",
          all("never reacts" in line for line in skill.splitlines() if "normal mode" in line), True)
    check("README tak mengklaim 'normal mode' untuk samewrite",
          all("never" in l or "not" in l or "ponytail" in l.lower() or "adhd" in l.lower()
              for l in readme.splitlines() if "normal mode" in l), True)

    # 4. versi: satu angka di plugin.json, marketplace.json, hook
    pj = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    mj = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
    check("marketplace metadata.version = plugin.json", mj["metadata"]["version"], pj["version"])

    # 5. SATU runtime kanonik: samewrite; edit-discipline = alias kompatibilitas, tak masuk listing
    skills = sorted(os.listdir(os.path.join(ROOT, "skills")))
    check("edit-discipline masih dikirim (alias)", "edit-discipline" in skills, True)
    check("samewrite dikirim", "samewrite" in skills, True)
    check("description samewrite <= 400 karakter (biaya listing tiap turn)",
          len(re.search(r"^description: (.*)$", fm, re.M).group(1)) <= 400, True)
    alias = open(os.path.join(ROOT, "skills", "edit-discipline", "SKILL.md"), encoding="utf-8").read()
    afm, abody = adapters.split(alias)
    check("alias: disable-model-invocation: true (nol biaya listing per turn)",
          "disable-model-invocation: true" in afm, True)
    check("alias: menunjuk ke samewrite", "samewrite" in abody, True)
    check("alias: kecil (< 1 kB badan)", len(abody) < 1024, True)
    for sec in ("## Context", "## Ask only if material", "## Root cause", "## Verification", "## Output"):
        check(f"kebijakan '{sec}' hanya ada di samewrite (nol duplikat runtime)",
              (sec in body, sec in abody), (True, False))

    # 6. hook output opsional = kalimat PERTAMA bagian "## Output" (satu teks kanonik, nol drift)
    out_sec = body.split("## Output", 1)[1]
    first = " ".join(out_sec.split("\n", 1)[1].split("Your own completed work")[0].split())
    inst = open(os.path.join(ROOT, "hooks", "install.sh"), encoding="utf-8").read()
    check("install.sh SAMEWRITE_OUTPUT_HOOK memuat kalimat pertama bagian Output SKILL.md persis", first in inst, True)
    check("kalimat hook <= 200 karakter (biaya per SessionStart)", len(first) <= 200, True)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
