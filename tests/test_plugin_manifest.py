#!/usr/bin/env python3
"""Uji manifest plugin + marketplace: sesuatu yang dipasang orang lain lewat satu perintah
harus gagal DI SINI, bukan di mesin mereka. Berdiri sendiri — jalankan berkas ini.

Yang diperiksa bukan "JSON-nya valid" saja: versi di plugin.json dan di entri marketplace
harus SAMA (kalau tidak, `claude plugin tag` menolak rilis), dan path skill harus benar-benar
memuat SKILL.md ber-front-matter — manifest yang menunjuk direktori kosong tetap lolos parse.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    pj = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    mj = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")))

    for k in ("name", "version", "description", "author", "license"):
        check(f"plugin.json punya '{k}'", k in pj, True)
    check("nama plugin tak kosong", bool(pj["name"].strip()), True)
    check("versi bergaya semver", len(pj["version"].split(".")), 3)

    check("marketplace punya owner", "owner" in mj, True)
    check("marketplace mendaftarkan tepat satu plugin", len(mj["plugins"]), 1)
    entry = mj["plugins"][0]
    check("entri marketplace menunjuk nama yang sama", entry["name"], pj["name"])

    # Versi entri boleh absen (diwarisi dari plugin.json); kalau ADA, harus sama.
    check("versi entri konsisten bila disebut",
          entry.get("version", pj["version"]), pj["version"])

    src = entry["source"] if isinstance(entry["source"], str) else entry["source"].get("path", "")
    check("source menunjuk direktori yang ada",
          os.path.isdir(os.path.join(ROOT, src)), True)
    check("source memuat plugin.json",
          os.path.isfile(os.path.join(ROOT, src, ".claude-plugin", "plugin.json")), True)

    skills = pj.get("skills", "./skills")
    skills = [skills] if isinstance(skills, str) else skills
    found = []
    for d in skills:
        d = os.path.join(ROOT, d)
        check(f"direktori skill ada: {os.path.relpath(d, ROOT)}", os.path.isdir(d), True)
        for name in sorted(os.listdir(d)):
            f = os.path.join(d, name, "SKILL.md")
            if os.path.isfile(f):
                found.append(f)
    check("minimal satu SKILL.md ditemukan", bool(found), True)

    for f in found:
        head = open(f, encoding="utf-8").read(2000)
        rel = os.path.relpath(f, ROOT)
        check(f"{rel} mulai dengan front matter", head.startswith("---\n"), True)
        fm = head.split("---\n")[1] if head.count("---\n") >= 2 else ""
        for k in ("name:", "description:"):
            check(f"{rel} front matter punya '{k}'", k in fm, True)
        # Nama skill = nama direktorinya; kalau beda, CLI memuat satu dan pengguna mencari yang lain.
        want = os.path.basename(os.path.dirname(f))
        got = [l.split(":", 1)[1].strip() for l in fm.splitlines() if l.startswith("name:")]
        check(f"{rel} nama skill = nama direktori", got[:1], [want])

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
