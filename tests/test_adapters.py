#!/usr/bin/env python3
"""Uji drift: adapters/ = hasil generate dari SKILL.md kanonik; permukaan perintah di README,
SKILL.md dan hook saling cocok; versi plugin/marketplace/hook satu angka. Berdiri sendiri."""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, os.path.join(ROOT, "hooks"))
import adapters  # noqa: E402
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

    # 3. permukaan perintah: yang didokumentasikan = yang dipahami hook, dan hanya /samewrite*
    check("SKILL.md mendokumentasikan /samewrite on|off|status", "/samewrite on|off|status" in skill, True)
    for cmd, want in [("/samewrite on", "on"), ("/samewrite off", "off"), ("/samewrite status", "status")]:
        check(f"hook memahami {cmd}", sm.parse(cmd), want)
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    foreign = re.findall(r"(?<![\w/])/(ponytail|caveman|i-have-adhd)\b", skill)
    check("SKILL.md tak mengklaim perintah plugin lain sebagai miliknya",
          all(f"/{x}" in ("/ponytail", "/caveman", "/i-have-adhd") for x in foreign), True)
    check("frasa 'normal mode' hanya muncul sebagai larangan di SKILL.md",
          all("never reacts" in line for line in skill.splitlines() if "normal mode" in line), True)
    check("README menyebut saklar bernama-ruang", "stop samewrite" in readme, True)

    # 4. versi: satu angka di plugin.json, marketplace.json, hook
    pj = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    mj = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))
    check("plugin.json = hook VERSION", pj["version"], sm.VERSION)
    check("marketplace metadata.version = plugin.json", mj["metadata"]["version"], pj["version"])

    # 5. dua skill terdaftar: yang lama tetap ada (kompatibilitas), yang baru kanonik
    skills = sorted(os.listdir(os.path.join(ROOT, "skills")))
    check("edit-discipline masih dikirim", "edit-discipline" in skills, True)
    check("samewrite dikirim", "samewrite" in skills, True)
    check("description samewrite <= 400 karakter (biaya listing tiap turn)",
          len(re.search(r"^description: (.*)$", fm, re.M).group(1)) <= 400, True)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
