#!/usr/bin/env python3
"""Baca ledger lapangan dan laporkan apa yang guard benar-benar lakukan.

Ledger ditulis hooks/write_noop_guard.py bila SAMEWRITE_LEDGER diset. Isinya
hanya ukuran dan hasil — tak ada path, nama berkas, atau isi. Alat ini
meringkasnya, dan dengan --markdown menghasilkan blok yang aman di-commit.

pakai: python3 tools/report.py LEDGER.jsonl [LEDGER2.jsonl ...] [--markdown] [--days N]
"""
import argparse, collections, json, os, sys, time

TOK_PER_BYTE = 1 / 3.14   # dari pengukuran o200k pada korpus kode; lihat docs/FINDINGS.md


def load(paths, days=None):
    cutoff = time.time() - days * 86400 if days else 0
    for p in paths:
        if not os.path.exists(p):
            continue
        for line in open(p, errors="replace"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("ts", 0) >= cutoff:
                yield r


def summarize(recs):
    s = collections.defaultdict(lambda: dict(checked=0, denied=0, bytes_saved=0))
    days = collections.defaultdict(lambda: dict(checked=0, denied=0, bytes_saved=0))
    for r in recs:
        h = r.get("host", "?")
        d = time.strftime("%Y-%m-%d", time.gmtime(r.get("ts", 0)))
        for bucket in (s[h], days[d]):
            if r.get("event") == "checked":
                bucket["checked"] += 1
            elif r.get("event") == "denied":
                bucket["denied"] += 1
                bucket["bytes_saved"] += r.get("bytes", 0)
    return s, days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ledgers", nargs="+")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--days", type=int)
    a = ap.parse_args()
    recs = list(load(a.ledgers, a.days))
    if not recs:
        print("ledger kosong — guard belum pernah berjalan, atau SAMEWRITE_LEDGER tak diset")
        return 0
    per_host, per_day = summarize(recs)
    tot_c = sum(v["checked"] for v in per_host.values())
    tot_d = sum(v["denied"] for v in per_host.values())
    tot_b = sum(v["bytes_saved"] for v in per_host.values())
    rate = 100 * tot_d / tot_c if tot_c else 0
    if a.markdown:
        print("<!-- dihasilkan tools/report.py — jangan disunting tangan -->")
        print(f"\n## Field data\n")
        print(f"Rentang: {min(per_day)} … {max(per_day)} ({len(per_day)} hari)\n")
        print(f"| host | Write diperiksa | ditolak | % | byte diselamatkan | ~token |")
        print(f"|---|---|---|---|---|---|")
        for h, v in sorted(per_host.items()):
            r = 100 * v["denied"] / v["checked"] if v["checked"] else 0
            print(f"| `{h}` | {v['checked']:,} | {v['denied']:,} | {r:.1f}% | "
                  f"{v['bytes_saved']:,} | {v['bytes_saved']*TOK_PER_BYTE:,.0f} |")
        print(f"| **total** | **{tot_c:,}** | **{tot_d:,}** | **{rate:.1f}%** | "
              f"**{tot_b:,}** | **{tot_b*TOK_PER_BYTE:,.0f}** |")
        print(f"\nRetrospektif pada 24 transcript memberi 15% (18/122). Lapangan: "
              f"**{rate:.1f}%** dari {tot_c:,} penulisan.")
        if tot_c >= 100 and rate < 2:
            print(f"\n> **Falsifier menyala.** README menyatakan: di bawah 2% pada sampel "
                  f"memadai, temuan ini tidak menggeneralisasi dan hook sebaiknya dicabut.")
    else:
        print(f"Write diperiksa {tot_c:,} · ditolak {tot_d:,} ({rate:.1f}%) · "
              f"byte diselamatkan {tot_b:,} (~{tot_b*TOK_PER_BYTE:,.0f} token)")
        for h, v in sorted(per_host.items()):
            r = 100 * v["denied"] / v["checked"] if v["checked"] else 0
            print(f"  {h:<20} periksa {v['checked']:>6,} · tolak {v['denied']:>5,} ({r:>5.1f}%)")
        for d in sorted(per_day)[-7:]:
            v = per_day[d]
            print(f"  {d}  periksa {v['checked']:>6,} · tolak {v['denied']:>5,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
