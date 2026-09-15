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
    desc = [l for l in fm.splitlines() if l.startswith("description:")][0].split(":", 1)[1].strip()
    for name, text in adapters.render().items():
        check(f"{name}: badan byte-identik dengan SKILL.md", text.endswith(body), True)
        if name.endswith("/SKILL.md"):
            # Dua kelas adapter berbentuk SKILL, dan syaratnya BERBEDA:
            #   passthrough  — berkas kanonik apa adanya (permukaan AgentSkills portabel)
            #   host-shaped  — metadata dibentuk ulang utk batas host (Hermes memotong 60 karakter)
            # Menuntut keduanya "jangan menyalin deskripsi kanonik" menghukum yang passthrough
            # justru karena melakukan hal yang benar.
            check(f"{name}: membawa front matter", text.startswith("---\n"), True)
            passthrough = name.startswith("agentskills/")
            if passthrough:
                check(f"{name}: byte-identik dgn SKILL.md kanonik", text == skill, True)
            else:
                check(f"{name}: deskripsi kanonik TIDAK disalin ke host ber-batas", desc in text, False)
        else:
            # Adapter berbentuk berkas instruksi: front matter apa pun hanya jadi sampah teks.
            check(f"{name}: tak membawa front matter Claude", "name: samewrite" in text, False)

    # Hermes memotong deskripsi ke 60 karakter DI PROMPT-nya. Deskripsi yang lebih panjang tidak
    # gagal — ia kehilangan ekor peruteannya diam-diam, dan itu lebih buruk daripada gagal.
    h = adapters.render()["hermes/samewrite/SKILL.md"]
    hdesc = [l for l in h.splitlines() if l.startswith("description:")][0].split(":", 1)[1].strip()
    check("hermes: deskripsi muat dalam batas host (60)", len(hdesc) <= adapters.HERMES_DESC_LIMIT, True)
    check("hermes: deskripsi tidak kosong", bool(hdesc), True)
    check("hermes: name sama dengan nama direktori (syarat linter Hermes)",
          [l for l in h.splitlines() if l.startswith("name:")][0].split(":", 1)[1].strip(),
          "samewrite")
    check("hermes: nol penanda khusus Claude yang diabaikan diam-diam di sana",
          "disable-model-invocation" in h, False)

    # Permukaan AgentSkills portabel: validator rujukan AgentSkills itu TERTUTUP — kunci top-level
    # tak dikenal = error. `disable-model-invocation` pada alias Claude persis kunci semacam itu,
    # dan Codex MENGABAIKANNYA diam-diam sehingga alias jadi TERLIHAT di sana. Jadi permukaan
    # portabel hanya boleh memuat skill yang sah menurut spec.
    ALLOWED = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
    ag = adapters.render()["agentskills/samewrite/SKILL.md"]
    agfm = ag.split("---", 2)[1]
    agkeys = [l.split(":", 1)[0].strip() for l in agfm.strip().splitlines()
              if ":" in l and not l.startswith((" ", "\t", "#"))]
    check("agentskills: nol kunci di luar spec", [k for k in agkeys if k not in ALLOWED], [])
    check("agentskills: name == nama direktori", 
          [l.split(":", 1)[1].strip() for l in agfm.strip().splitlines()
           if l.startswith("name:")][0], "samewrite")
    check("agentskills: badan byte-identik dgn kanonik", ag.endswith(body), True)
    check("agentskills: alias khusus-Claude TIDAK diekspor",
          "disable-model-invocation" in ag, False)

    cx = json.load(open(os.path.join(ROOT, ".codex-plugin", "plugin.json")))
    cpj = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    check("codex manifest menunjuk permukaan portabel, bukan skills/",
          cx.get("skills"), "./adapters/agentskills")
    check("codex manifest versinya sama dgn plugin.json", cx.get("version"), cpj["version"])

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

    # 5b. SATU kosakata hash, dan badan yang benar-benar identik di setiap host.
    # `endswith(body)` di atas memakai definisi yang dinormalkan (lstrip). Cek ini memakai byte
    # MENTAH sesudah delimiter penutup — definisi yang dipakai setiap angka yang kita terbitkan.
    # Tanpa ini, satu baris komentar di badan adapter lolos diam-diam dan klaim "identik di mana
    # pun" berubah jadi klaim yang butuh catatan kaki.
    surfaces = {name: adapters.hashes(os.path.join(ROOT, path))
                for name, path in adapters.SURFACES}
    bodies = {h[2] for h in surfaces.values()}
    check("BODY_SHA256 identik di keempat host", len(bodies), 1)
    canon = surfaces["CLAUDE (canonical)"]
    check("BODY_SHA256 kanonik = badan mentah sesudah front matter",
          canon[2], adapters.hashes(os.path.join(ROOT, "skills/samewrite/SKILL.md"))[2])
    # Hermes HARUS berbeda sebagai berkas — kalau tidak, deskripsinya tidak dipendekkan sama
    # sekali dan host memotongnya sendiri, yang justru mau dihindari.
    check("FULL_FILE_SHA256 Hermes berbeda dari kanonik (metadata memang dibentuk ulang)",
          surfaces["HERMES"][0] != canon[0], True)
    r = subprocess.run([sys.executable, adapters.__file__, "--hashes"], capture_output=True, text=True)
    check("adapters --hashes hijau", r.returncode, 0)
    check("laporan hash menyebut CROSS_HOST_BODY_IDENTITY = PASS",
          "CROSS_HOST_BODY_IDENTITY = PASS" in r.stdout, True)

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
