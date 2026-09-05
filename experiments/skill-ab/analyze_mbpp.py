#!/usr/bin/env python3
"""MBPP minimal-change analysis, exactly as PREREGISTRATION_mbpp_minimal_change.md
registered it: correctness gate first, characters primary by exact paired permutation,
non-blank lines secondary by exact sign test, floors printed beside every p."""
import itertools, json, os, sys
from collections import Counter
from math import comb
import mbpp_select as select

HERE = os.path.dirname(os.path.abspath(__file__))


def exact_perm_p(diffs):
    obs = abs(sum(diffs))
    hit = sum(1 for s in itertools.product((1, -1), repeat=len(diffs))
              if abs(sum(x * y for x, y in zip(s, diffs))) >= obs - 1e-12)
    return hit / 2 ** len(diffs)


def sign_test(k, n):
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def pairs(rows):
    by = {}
    for r in rows:
        tid, arm = r.get("task_id"), r.get("arm")
        if not isinstance(tid, int) or arm not in ("plain", "oneline"):
            raise SystemExit(f"invalid task/arm record: {r!r}")
        arms = by.setdefault(tid, {})
        if arm in arms:
            raise SystemExit(f"duplicate record for mbpp_{tid} {arm}")
        arms[arm] = r
    keep, dropped = {}, []
    for tid, arms in sorted(by.items()):
        if "plain" not in arms or "oneline" not in arms:
            dropped.append((tid, "missing arm")); continue
        bad = [a for a, r in arms.items()
               if r["rc"] != 0 or not r["passing"] or r["chars"] == 0]
        if bad:
            dropped.append((tid, "gate/empty: " + ",".join(sorted(bad)))); continue
        keep[tid] = arms
    return keep, dropped


def main(path="mbpp_minimal_change.jsonl"):
    rows = [json.loads(l) for l in open(os.path.join(HERE, path)) if l.strip()]
    expected = {r["task_id"] for r in select.selected()}
    wanted_records = {(task_id, arm) for task_id in expected
                      for arm in ("plain", "oneline")}
    observed_records = [(r.get("task_id"), r.get("arm")) for r in rows]
    if len(rows) != 40 or set(observed_records) != wanted_records or \
            any(n != 1 for n in Counter(observed_records).values()):
        raise SystemExit(
            "aborted study: expected exactly 40 records (both arms of the 20 "
            f"frozen selected tasks), got {len(rows)} records for "
            f"{len({task_id for task_id, _ in observed_records})} tasks"
        )
    keep, dropped = pairs(rows)
    print(f"runs={len(rows)}  pairs kept={len(keep)}  dropped={len(dropped)}")
    for tid, why in dropped:
        print(f"    dropped mbpp_{tid}: {why}")
    if not keep:
        raise SystemExit("no pairs survived - aborted study")

    # PRIMARY: characters, proportional delta per task, exact paired permutation
    d = [(keep[t]["oneline"]["chars"] - keep[t]["plain"]["chars"]) / keep[t]["plain"]["chars"]
         for t in keep]
    tp = sum(keep[t]["plain"]["chars"] for t in keep)
    tq = sum(keep[t]["oneline"]["chars"] for t in keep)
    print(f"\nPRIMARY  characters: {tp:,} -> {tq:,}  ({100*(tq-tp)/tp:+.1f}% pooled)")
    print(f"  mean per-task proportional delta {100*sum(d)/len(d):+.1f}%, "
          f"smaller in {sum(1 for x in d if x < 0)}/{len(d)}")
    print(f"  exact paired permutation, two-sided: p = {exact_perm_p(d):.5f}  "
          f"(threshold 0.05)")

    # SECONDARY: non-blank lines, exact sign test
    lo = sum(1 for t in keep if keep[t]["oneline"]["lines"] < keep[t]["plain"]["lines"])
    hi = sum(1 for t in keep if keep[t]["oneline"]["lines"] > keep[t]["plain"]["lines"])
    n = lo + hi
    print(f"\nSECONDARY  non-blank lines: smaller in {lo}, larger in {hi}, "
          f"tied in {len(keep)-n}")
    print(f"  exact two-sided sign test on {n} non-tied tasks: p = {sign_test(max(lo,hi), n):.5f}"
          f"  (floor {sign_test(n, n):.6f})")

    nf = sum(keep[t][a]["new_files"] for t in keep for a in ("plain", "oneline"))
    print(f"\nrecorded, not tested: {nf} extra files created across all runs")
    print(f"\n{'task':>10} {'plain':>7} {'oneline':>8} {'delta':>8}   lines")
    for t in keep:
        p, q = keep[t]["plain"], keep[t]["oneline"]
        print(f"  mbpp_{t:<5d} {p['chars']:>7} {q['chars']:>8} "
              f"{100*(q['chars']-p['chars'])/p['chars']:>7.1f}%   {p['lines']:>3} -> {q['lines']:<3}")


if __name__ == "__main__":
    main(*sys.argv[1:])
