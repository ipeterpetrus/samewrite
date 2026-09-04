#!/usr/bin/env python3
"""Minimal-change contrast, analysed the way PREREGISTRATION_minimal_change_english.md
says: correctness gate first, task as the unit, exact sign test, floor printed next to p.

Endpoint is non-blank lines in mod.py, conditional on pytest passing. A run that does not
pass is not a smaller solution, it is a broken one."""
import json, math, os, sys
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    rows = [json.loads(l) for l in open(os.path.join(HERE, name)) if l.strip()]
    return rows


def sign_test(k, n):
    """Two-sided exact sign test on k successes out of n non-tied trials."""
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def floor_p(n):
    return sign_test(n, n) if n else 1.0


def per_task(rows):
    """Sum lines per (task, arm) over repeats, keeping only pairs where BOTH arms
    produced working code. A pair is dropped whole, never one-sided."""
    by = {}
    for r in rows:
        if r["rc"] != 0 or not r["passing"]:
            continue
        by.setdefault((r["fixture"], r["rep"]), {})[r["arm"]] = r["lines"]
    agg, dropped = {}, 0
    for (task, rep), arms in sorted(by.items()):
        if "plain" not in arms or "oneline" not in arms:
            dropped += 1
            continue
        a, b = agg.setdefault(task, [0, 0])
        agg[task] = [a + arms["plain"], b + arms["oneline"]]
    return agg, dropped


def report(label, name):
    rows = load(name)
    agg, dropped = per_task(rows)
    n_runs = len(rows)
    broken = sum(1 for r in rows if r["rc"] != 0 or not r["passing"])
    print(f"\n=== {label} — one sentence vs no instruction, non-blank lines ===")
    print(f"  runs={n_runs}  failed the correctness gate={broken}  pairs dropped={dropped}")
    lower = sum(1 for p, q in agg.values() if q < p)
    tied = sum(1 for p, q in agg.values() if q == p)
    n = len(agg) - tied
    k = lower
    p = sign_test(k, n)
    tp = sum(p for p, _ in agg.values()); tq = sum(q for _, q in agg.values())
    print(f"  TASK level (the registered primary): smaller in {lower}/{len(agg)} tasks"
          f"{f', {tied} tied' if tied else ''}")
    print(f"    exact two-sided sign test on {n} non-tied tasks: p = {p:.4f}"
          f"   (floor for {n} tasks = {floor_p(n):.4f})")
    print(f"    total lines {tp} -> {tq}  ({100*(tq-tp)/tp:+.1f}%)")
    for t in sorted(agg):
        a, b = agg[t]
        print(f"      {t:16s} {a:>4} -> {b:>4}  {100*(b-a)/a:+6.1f}%")
    return {t: (b - a) / a for t, (a, b) in agg.items()}


def interaction(en, id_):
    keys = sorted(set(en) & set(id_))
    d = [en[k] - id_[k] for k in keys]
    k = sum(1 for x in d if x > 0)
    n = sum(1 for x in d if x != 0)
    print("\n=== interaction: does the effect DIFFER between English and Indonesian? ===")
    for key in keys:
        print(f"  {key:16s} id {100*id_[key]:+6.1f}%  en {100*en[key]:+6.1f}%  "
              f"diff {100*(en[key]-id_[key]):+6.1f} pp")
    print(f"  English larger in {k}/{n} non-tied tasks, exact two-sided sign test "
          f"p = {sign_test(max(k, n-k), n):.4f} (floor {floor_p(n):.4f})")
    print("  Non-significant here means the data do not support claiming the magnitudes")
    print("  differ. It is not evidence that they are equal.")


if __name__ == "__main__":
    en = report("English (primary)", "minimal_change_en.jsonl")
    id_ = report("Indonesian", "minimal_change_id.jsonl")
    interaction(en, id_)
