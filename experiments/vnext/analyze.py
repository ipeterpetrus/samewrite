#!/usr/bin/env python3
"""Analisis pilot vNext — kontras yang DIPRA-REGISTRASI saja (PREREGISTRATION.md), uji tanda
berpasangan per fixture, dan daftar fixture yang KALAH disebut namanya.

    python3 analyze.py runs/pilot1.jsonl [--markdown]
"""
import collections, json, math, sys

CONTRASTS = [("D", "C", "H1 candidate vs current"), ("D", "A", "vs bare"), ("D", "B", "vs one sentence"),
             ("D2", "D", "H4 hooks tax"), ("H", "E", "H2/H3 +vNext on ponytail"),
             ("I", "F", "H2/H3 +vNext on i-have-adhd"), ("J", "G", "H2/H3 +vNext on both")]


def sign_p(k, n):
    """two-sided exact binomial p for k of n successes under p=0.5"""
    if n == 0:
        return float("nan")
    lo = min(k, n - k)
    tail = sum(math.comb(n, i) for i in range(lo + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["arm"]][(r["fixture"], r.get("rep", 0))] = r   # pasangan = (fixture, ulangan)
    return rows, by


def main(path, md=False):
    rows, by = load(path)
    arms = sorted(by, key=lambda a: (len(a), a))
    fixtures = sorted({(r["fixture"], r.get("rep", 0)) for r in rows})
    fname = lambda f: f[0] if f[1] == 0 else f"{f[0]}#r{f[1]}"
    excluded = [(r["arm"], r["fixture"], "INFRA_ERROR" if r["verdict"] == "INFRA_ERROR" else
                 "treatment" if not r.get("treatment_ok") else "rc/transcript")
                for r in rows if not r.get("treatment_ok") or r.get("rc") != 0 or "transcript" not in r
                or r["verdict"] == "INFRA_ERROR"]
    print(f"{len(rows)} run · {len(arms)} arms · {len(fixtures)} fixtures · excluded {len(excluded)}")
    for e in excluded:
        print("  EXCLUDED", e)

    def ok(r):
        return r.get("treatment_ok") and r.get("rc") == 0 and "transcript" in r and r["verdict"] != "INFRA_ERROR"

    print("\nper arm — ROOT count, mean weighted context (ok rows), mean output tokens, mean turns, listing bytes")
    hdr = "| arm | ROOT/n | weighted ctx | output tok | turns | Read B | Bash B | listing B | verdicts |"
    print(hdr if md else hdr.replace("|", " "))
    if md:
        print("|---|---|---|---|---|---|---|---|---|")
    for a in arms:
        rs = [r for r in by[a].values() if ok(r)]
        n = len(by[a])
        root = sum(1 for r in by[a].values() if r["verdict"] == "ROOT")
        mean = lambda k: (sum(k(r) for r in rs) / len(rs)) if rs else float("nan")
        vs = " ".join(f"{fname(f)[:6]}={by[a][f]['verdict'][:4]}" for f in fixtures if f in by[a])
        line = (f"| {a} | {root}/{n} | {mean(lambda r: r['weighted_input']):,.0f} | "
                f"{mean(lambda r: r['usage'].get('output_tokens', 0)):,.0f} | {mean(lambda r: r['turns']):.1f} | "
                f"{mean(lambda r: r['bytes_by_source'].get('Read', 0)):,.0f} | "
                f"{mean(lambda r: r['bytes_by_source'].get('Bash', 0)):,.0f} | "
                f"{mean(lambda r: r.get('listing_bytes', 0)):,.0f} | {vs} |")
        print(line if md else line.replace("|", " "))

    print("\npre-registered contrasts (paired by fixture; only rows valid in BOTH arms)")
    for x, y, label in CONTRASTS:
        if x not in by or y not in by:
            continue
        pairs = [f for f in fixtures if f in by[x] and f in by[y] and ok(by[x][f]) and ok(by[y][f])]
        rx = sum(1 for f in pairs if by[x][f]["verdict"] == "ROOT")
        ry = sum(1 for f in pairs if by[y][f]["verdict"] == "ROOT")
        both = [f for f in pairs if by[x][f]["verdict"] == "ROOT" and by[y][f]["verdict"] == "ROOT"]
        cheaper = [f for f in both if by[x][f]["weighted_input"] < by[y][f]["weighted_input"]]
        dearer = [f for f in both if by[x][f]["weighted_input"] > by[y][f]["weighted_input"]]
        ties = len(both) - len(cheaper) - len(dearer)       # seri dibuang dari uji tanda
        deltas = [by[x][f]["weighted_input"] / by[y][f]["weighted_input"] - 1 for f in both]
        med = sorted(deltas)[len(deltas) // 2] if deltas else float("nan")
        nn = len(cheaper) + len(dearer)
        print(f"  {x} vs {y} ({label}): n={len(pairs)} ROOT {rx} vs {ry}; both-ROOT {len(both)}: "
              f"{x} cheaper in {len(cheaper)}/{nn}{' (+%d tie)' % ties if ties else ''} "
              f"(sign p={sign_p(len(cheaper), nn):.3f}), median Δweighted {med:+.1%}")
        lost = [f for f in pairs if by[x][f]["verdict"] != "ROOT" and by[y][f]["verdict"] == "ROOT"]
        if lost:
            print(f"     correctness LOST by {x} on: {', '.join(map(fname, lost))}")
        if dearer:
            print(f"     {x} dearer on: {', '.join(map(fname, dearer))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], "--markdown" in sys.argv))
