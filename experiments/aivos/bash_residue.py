#!/usr/bin/env python3
"""How large is Bash output ACTUALLY, as it reaches a model's context?

The bash-output-shaping candidate rests on one premise: that Bash results are big enough, often
enough, for bounding them to be worth a rule. Claude Code is documented to cap Bash output and
spill the remainder to a file, which — if true at the size claimed — would mean the platform
already does what the candidate proposes, and the candidate is duplicated platform behaviour
rather than an improvement.

That is a question for the transcripts, not for the documentation. This measures the real
distribution of tool-result sizes per source over a real archive, so the candidate is decided by
what reaches the model rather than by what a manual says should.

    python3 experiments/aivos/bash_residue.py                    # auto-discovered profiles
    python3 experiments/aivos/bash_residue.py --max-files 400 --json

Read-only, offline, aggregates only: sizes and counts, never content.
"""
import argparse, collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import carry, profiles  # noqa: E402

# The documented Claude Code behaviour this is testing, so the numbers have something to falsify.
CLAIMED_INLINE = 2_000        # bytes said to stay inline in context
CLAIMED_CAP = 30_000          # bytes said to be the total cap before spilling to a file


def pct(sorted_vals, p):
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, int(round((p / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", nargs="*", default=None)
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--min-turns", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    paths, _ = profiles.resolve(a.scan or [])
    paths = carry.bounded_paths(paths, a.max_files)   # one definition of "the newest N"

    sizes = collections.defaultdict(list)
    total = collections.Counter()
    sessions = scanned = 0
    for p in paths:
        try:
            turn, items, usage, _meta = carry.scan_full(p)
        except Exception:
            continue
        scanned += 1
        if turn < a.min_turns:
            continue
        sessions += 1
        for _t, b, src in items:
            k = carry.bucket(src)
            sizes[k].append(b)
            total[k] += b

    rows = []
    for k in sorted(sizes, key=lambda x: -total[x]):
        v = sorted(sizes[k])
        n = len(v)
        over_inline = sum(1 for x in v if x > CLAIMED_INLINE)
        over_cap = sum(1 for x in v if x > CLAIMED_CAP)
        rows.append(dict(source=k, n=n, total_bytes=total[k], median=pct(v, 50), p90=pct(v, 90),
                         p99=pct(v, 99), maximum=v[-1] if v else 0,
                         over_inline_pct=round(100.0 * over_inline / n, 1) if n else 0.0,
                         over_cap_pct=round(100.0 * over_cap / n, 1) if n else 0.0,
                         over_cap_n=over_cap,
                         bytes_above_cap=sum(x - CLAIMED_CAP for x in v if x > CLAIMED_CAP)))

    grand = sum(total.values()) or 1
    if a.json:
        print(json.dumps(dict(sessions=sessions, scanned=scanned, claimed_inline=CLAIMED_INLINE,
                              claimed_cap=CLAIMED_CAP, rows=rows), indent=2))
        return 0

    print(f"tool-result size distribution — {sessions} sessions over {scanned} transcripts")
    print(f"testing the documented Claude Code behaviour: ~{CLAIMED_INLINE:,} B inline, "
          f"{CLAIMED_CAP:,} B cap then spill to file\n")
    print(f"{'source':<20}{'n':>8}{'share':>8}{'median':>9}{'p90':>9}{'p99':>10}{'max':>11}"
          f"{'>2KB':>8}{'>30KB':>8}")
    for r in rows:
        print(f"{r['source']:<20}{r['n']:>8}{100.0 * r['total_bytes'] / grand:>7.1f}%"
              f"{r['median']:>9,}{r['p90']:>9,}{r['p99']:>10,}{r['maximum']:>11,}"
              f"{r['over_inline_pct']:>7.1f}%{r['over_cap_pct']:>7.1f}%")
    bash = next((r for r in rows if r["source"] == "Bash"), None)
    if bash:
        print()
        if bash["over_cap_n"] == 0:
            print(f"VERDICT: no Bash result exceeds {CLAIMED_CAP:,} B. The documented cap is "
                  f"consistent with this archive, and a SameWrite rule that caps Bash output "
                  f"would duplicate platform behaviour.")
        else:
            print(f"VERDICT: {bash['over_cap_n']:,} Bash results ({bash['over_cap_pct']}%) exceed "
                  f"{CLAIMED_CAP:,} B, totalling {bash['bytes_above_cap']:,} B above it. The "
                  f"documented cap does NOT describe what reaches the model here.")
        print(f"Bash results above the inline claim: {bash['over_inline_pct']}% of "
              f"{bash['n']:,}; median {bash['median']:,} B, p90 {bash['p90']:,} B.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
