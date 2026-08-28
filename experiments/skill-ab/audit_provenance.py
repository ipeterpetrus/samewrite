#!/usr/bin/env python3
"""Audit ASAL PERBAIKAN — menjawab keberatan terkuat panel adv-max ronde-7.

Panel: "uji TETANGGA bisa dilewati. Agen bisa mengeraskan ketiga nilai yang kebetulan diuji
di dalam KODE dan lulus dua-duanya tanpa memperbaiki kelasnya. Kalau begitu, sebagian vonis
ROOT di ronde-ronde sebelumnya mungkin pelarian, dan cerita langit-langitnya bertumpu pada
tambalan yang tak pernah diperiksa."

Cek ini murah dan mekanis: untuk tiap run, bandingkan isi berkas kerja dengan isi awalnya,
lalu tanya satu hal — apakah berkas yang MEMUAT AKAR ikut berubah?

  ROOT + berkas-akar tersentuh   -> perbaikan kelas yang sah
  ROOT + berkas-akar UTUH        -> PELARIAN: lulus dua uji tanpa menyentuh akarnya
  bukan ROOT                     -> tak relevan di sini

Ini bukti STRUKTURAL, bukan tambahan uji: uji apa pun yang kutulis tetap bisa dilewati,
sedangkan "berkas akar tak pernah disunting" tak bisa dibantah.
"""
import json, os, sys, collections

ROOT_FILE = {
    "scale_table": "data/currencies.py",
    "config_keys": "conf/parse.py",
    "sibling_callers": "util/text.py",
    "subclass_family": "base/shape.py",
    "handler_registry": "handlers/impl.py",
    # ronde 3
    "flag_chain": "conf/defaults.py",
    "classvar_shared": "base/entity.py",
    "swallow_deep": "net/retry.py",
    "pagination_edge": "core/paginate.py",
    "sort_group": "services/grouping.py",
}


def original(fixture, relpath, mods):
    for m in mods:
        if fixture in m.F and relpath in m.F[fixture]["files"]:
            return m.F[fixture]["files"][relpath]
    return None


def main(paths):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    mods = []
    for name in ("fixtures4", "fixtures3", "fixtures2", "fixtures"):
        try:
            mods.append(__import__(name))
        except Exception:
            pass
    tally = collections.Counter()
    escapes = []
    for path in paths:
        for line in open(path):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("rc") != 0 or r.get("verdict") != "ROOT":
                continue
            fx, work = r["fixture"], r["work"]
            rel = ROOT_FILE.get(fx)
            if not rel:
                continue
            p = os.path.join(work, fx, rel)
            base = original(fx, rel, mods)
            if base is None or not os.path.exists(p):
                tally[(fx, "tak-terperiksa")] += 1
                continue
            touched = open(p).read() != base
            tally[(fx, "akar disentuh" if touched else "PELARIAN")] += 1
            if not touched:
                escapes.append((os.path.basename(path), fx, r["arm"], r.get("rep")))
    print(f"{'fixture':18s} {'status':16s} n")
    for (fx, st), n in sorted(tally.items()):
        print(f"{fx:18s} {st:16s} {n}")
    print()
    tot = sum(tally.values())
    esc = sum(n for (_, st), n in tally.items() if st == "PELARIAN")
    unk = sum(n for (_, st), n in tally.items() if st == "tak-terperiksa")
    print(f"vonis ROOT diperiksa: {tot} · pelarian: {esc} · tak-terperiksa: {unk}")
    if escapes:
        print("\nPELARIAN (ROOT tanpa menyentuh berkas akar):")
        for e in escapes:
            print("  ", e)


if __name__ == "__main__":
    main(sys.argv[1:])
