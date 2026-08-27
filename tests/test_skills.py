#!/usr/bin/env python3
"""Uji tools/skills.py: parsing listing, atribusi pemakaian lintas nama, dan
janji privasinya. Berdiri sendiri — jalankan berkas ini, tanpa runner."""
import json, os, subprocess, sys, tempfile

SK = os.path.join(os.path.dirname(__file__), "..", "tools", "skills.py")
sys.path.insert(0, os.path.dirname(SK))
import skills  # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


LISTING = (
    "The following skills are available:\n\n"
    "- alpha: does a thing.\n"
    "- plug:beta: does another thing,\n"
    "  and the description wraps onto a second line.\n"
    "- gamma: never used by anyone.\n"
)


def main():
    ent = skills.parse_listing(LISTING)
    check("entri terparse", [n for n, _ in ent], ["alpha", "plug:beta", "gamma"])
    check("baris pembungkus milik entri sebelumnya",
          ent[1][1], len("- plug:beta: does another thing,\n")
                     + len("  and the description wraps onto a second line.\n"))
    check("header di atas entri pertama tak dibebankan",
          sum(b for _, b in ent) < len(LISTING), True)

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.jsonl")
        with open(p, "w") as fh:
            fh.write(json.dumps({"type": "attachment", "attachment": {
                "type": "skill_listing", "content": LISTING}}) + "\n")
            fh.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "1", "name": "Skill",
                 "input": {"skill": "alpha"}}]}}) + "\n")
            # dipanggil lewat nama ber-plugin
            fh.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "2", "name": "Skill",
                 "input": {"skill": "plug:beta"}}]}}) + "\n")
            # dan lewat slash tanpa awalan plugin: entri yang sama, bukan entri baru
            fh.write(json.dumps({"type": "user",
                                 "message": {"content": "<command-name>/beta</command-name>"}}) + "\n")
        listing, uses, sess = skills.scan([p])
        check("listing terambil dari attachment", listing, LISTING)
        rows = dict((r[0], r[2]) for r in skills.tally(skills.parse_listing(listing),
                                                       uses, sess))
        check("panggilan Skill terhitung", rows["alpha"], 1)
        check("nama ber-plugin dan slash polos jatuh ke entri yang sama", rows["plug:beta"], 2)
        check("entri tak terpakai tetap nol", rows["gamma"], 0)

        out = subprocess.run([sys.executable, SK, p], capture_output=True, text=True).stdout
        check("dingin dihitung dan dihargai", "1/3 entries" in out, True)
        check("keluaran menyebut jalur tindakan", "skillOverrides" in out, True)
        check("keluaran tak memuat path transcript", d in out, False)

        md = subprocess.run([sys.executable, SK, p, "--markdown"],
                            capture_output=True, text=True).stdout
        check("markdown: tiap entri satu baris tabel",
              sum(1 for x in md.splitlines() if x.startswith("| `")), 3)

        # ambang --min-uses menggeser himpunan dingin, bukan cuma labelnya
        out2 = subprocess.run([sys.executable, SK, p, "--min-uses", "1"],
                              capture_output=True, text=True).stdout
        check("--min-uses 1 menarik alpha ke himpunan dingin", "2/3 entries" in out2, True)

        # tanpa listing: gagal jujur, bukan tabel kosong
        q = os.path.join(d, "empty.jsonl")
        open(q, "w").write(json.dumps({"type": "assistant", "message": {"content": []}}) + "\n")
        r = subprocess.run([sys.executable, SK, q], capture_output=True, text=True)
        check("tanpa listing -> exit bukan-nol", r.returncode, 1)
        check("tanpa listing -> katakan, jangan karang", "nothing to price" in r.stdout, True)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
