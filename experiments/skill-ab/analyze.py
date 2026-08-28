#!/usr/bin/env python3
"""Ringkas hasil uji perilaku. Statistik ditulis apa adanya, termasuk daya ujinya."""
import collections, json, math, sys

ORDER = ["ROOT", "SYMPTOM", "FAIL", "INVALID"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0, c - h), 100 * min(1, c + h))


def main(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        by[r["arm"]][r["verdict"]] += 1
    print(f"n = {len(rows)} run · model {rows[0]['model']}\n")
    print(f"{'lengan':8s} " + " ".join(f"{v:>8s}" for v in ORDER) + f" {'n':>4s} {'ROOT%':>7s} {'CI95':>13s}")
    for arm in ("plain", "skill"):
        c = by[arm]
        n = sum(c.values())
        lo, hi = wilson(c["ROOT"], n)
        print(f"{arm:8s} " + " ".join(f"{c[v]:>8d}" for v in ORDER)
              + f" {n:>4d} {100*c['ROOT']/n if n else 0:>6.1f}% {lo:>5.0f}-{hi:<5.0f}")
    print()
    print("per fixture (ROOT/n):")
    per = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for r in rows:
        per[r["fixture"]][r["arm"]][r["verdict"]] += 1
    wins = ties = losses = 0
    for f in sorted(per):
        cells = []
        for arm in ("plain", "skill"):
            c = per[f][arm]
            n = sum(c.values())
            cells.append(f"{c['ROOT']}/{n}")
        a = per[f]["plain"]["ROOT"] / max(1, sum(per[f]["plain"].values()))
        b = per[f]["skill"]["ROOT"] / max(1, sum(per[f]["skill"].values()))
        mark = "skill>" if b > a else ("plain>" if a > b else "  =   ")
        wins += b > a
        losses += a > b
        ties += a == b
        print(f"  {f:12s} plain {cells[0]:>6s}   skill {cells[1]:>6s}   {mark}")
    print(f"\nuji tanda per-fixture: skill menang {wins}, seri {ties}, plain menang {losses}")
    k, n = wins, wins + losses
    if n:
        p = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
        print(f"  p satu-sisi (binomial, n={n} fixture tak-seri) = {p:.3f}")
    else:
        print("  nol fixture yang tak seri -> uji tanda tak punya daya sama sekali")
    print("\nJUJUR: fixture = 6, ulangan = 3. Daya uji rendah; ini PILOT, bukan vonis.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results.jsonl")
