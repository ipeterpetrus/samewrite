#!/usr/bin/env python3
"""Nilai ulang verdict dari direktori kerja yang tersimpan (diff agen = bukti) memakai
`rig.verdict()` versi sekarang. Dipakai sekali pada pilot1: scorer awal menghitung
`.pytest_cache` sebagai berkas yang ditambahkan agen. Baris asli tak diubah; keluaran baru
membawa `verdict_original` + `rescored=true`."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig
from fixtures import FIXTURES

src, dst = sys.argv[1], sys.argv[2]
changed = 0
with open(dst, "w") as out:
    for line in open(src):
        r = json.loads(line)
        d = os.path.join(r["work"], r["fixture"])
        stdout = open(os.path.join(d, "_stdout.txt")).read() if os.path.exists(os.path.join(d, "_stdout.txt")) else ""
        v, ch, ex = rig.verdict(FIXTURES[r["fixture"]], d, stdout)
        r.update(verdict_original=r["verdict"], verdict=v, files_changed=ch, files_added=ex, rescored=True)
        changed += v != r["verdict_original"]
        out.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"rescored -> {dst}; verdict changed on {changed} rows")
