#!/usr/bin/env python3
"""Terjemahkan token terukur jadi biaya API model frontier.

JUJUR: run-nya dieksekusi pada SATU model. Menghargai jumlah token yang sama dengan
tarif model lain adalah TERJEMAHAN BIAYA, bukan pengukuran perilaku model itu — model
lain akan memakai jumlah token yang berbeda. Tabel ini menjawab "kalau beban token
seperti ini berjalan di model X, berapa tagihannya", bukan "model X akan seboros ini".

Tarif per 1 juta token (skill claude-api, cache 2026-06-24). Cache write 5m = 1,25x
input; cache read = 0,1x input.
"""
import collections, glob, json, os, statistics as st, sys

RATE = {                      # nama: (input, output)
    "Fable 5":   (10.00, 50.00),
    "Opus 5":    (5.00, 25.00),
    "Sonnet 5":  (2.00, 10.00),
    "Haiku 4.5": (1.00, 5.00),
}
ROOTS = [os.path.expanduser("~/.claude/projects"),
         os.path.expanduser("~/.claude-pro/projects")]


def slug(p):
    return "-" + p.strip("/").replace("/", "-").replace("_", "-")


def toks(work, fixture, extra_roots=()):
    s = slug(os.path.join(work, fixture))
    tot, seen = collections.Counter(), set()
    for R in list(ROOTS) + list(extra_roots):
        for f in glob.glob(os.path.join(R, s, "*.jsonl")):
            b = os.path.basename(f)
            if b in seen:
                continue
            seen.add(b)
            for line in open(f, errors="replace"):
                if '"usage"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                u = (o.get("message") or {}).get("usage") or {}
                for k in ("input_tokens", "output_tokens",
                          "cache_read_input_tokens", "cache_creation_input_tokens"):
                    tot[k] += u.get(k) or 0
    return tot


def cost(t, rate_in, rate_out):
    return (t["input_tokens"] * rate_in
            + t["cache_creation_input_tokens"] * rate_in * 1.25
            + t["cache_read_input_tokens"] * rate_in * 0.10
            + t["output_tokens"] * rate_out) / 1e6


def main(path, cfg_projects=None):
    extra = [cfg_projects] if cfg_projects else []
    rows = [json.loads(l) for l in open(path) if l.strip()]
    agg = collections.defaultdict(collections.Counter)
    n = collections.Counter()
    miss = 0
    for r in rows:
        t = toks(r["work"], r["fixture"], extra)
        if not sum(t.values()):
            miss += 1
            continue
        agg[r["arm"]].update(t)
        n[r["arm"]] += 1
    if miss:
        print(f"# {miss}/{len(rows)} run tanpa transcript — dikeluarkan dari hitungan biaya")
    print(f"{'lengan':8s} {'run':>4s} {'in':>9s} {'out':>9s} {'c_read':>11s} {'c_write':>10s}")
    for arm in ("plain", "skill"):
        if not n[arm]:
            continue
        t = agg[arm]
        print(f"{arm:8s} {n[arm]:>4d} {t['input_tokens']:>9,} {t['output_tokens']:>9,} "
              f"{t['cache_read_input_tokens']:>11,} {t['cache_creation_input_tokens']:>10,}")
    if not (n["plain"] and n["skill"]):
        print("\n(butuh kedua lengan untuk tabel biaya)")
        return
    print(f"\nbiaya API per SATU tugas debugging (rata-rata {n['plain']} vs {n['skill']} run):")
    print(f"{'model':10s} {'tanpa skill':>13s} {'pakai skill':>13s} {'selisih':>11s} {'delta':>8s}")
    for m, (ri, ro) in RATE.items():
        a = cost(agg["plain"], ri, ro) / n["plain"]
        b = cost(agg["skill"], ri, ro) / n["skill"]
        print(f"{m:10s} {'$%.4f' % a:>13s} {'$%.4f' % b:>13s} {'+$%.4f' % (b - a):>11s} "
              f"{'%+.0f%%' % (100 * (b - a) / a):>8s}")
    print("\nper 1.000 tugas:")
    for m, (ri, ro) in RATE.items():
        a = 1000 * cost(agg["plain"], ri, ro) / n["plain"]
        b = 1000 * cost(agg["skill"], ri, ro) / n["skill"]
        print(f"  {m:10s} tanpa ${a:>8,.2f}  pakai ${b:>8,.2f}  selisih +${b-a:>8,.2f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results2.jsonl",
         sys.argv[2] if len(sys.argv) > 2 else None)
