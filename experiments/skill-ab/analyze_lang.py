#!/usr/bin/env python3
"""Cross-language contrast, with the three things round 22 said were missing:
task-level clustering, an interaction test, and a gate that can fail.

Run-level pairing answers "on these four fixtures, does the sentence save tokens?"
It does NOT answer "does it save tokens on tasks in general" - four tasks is four
observations however many times each is repeated. Both are reported, separately."""
import json, itertools, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    d = {}
    for line in open(os.path.join(HERE, name)):
        o = json.loads(line)
        d[(o["task"], o["rep"], o["arm"])] = o
    return d


def paired(d, a, b):
    out = []
    for (t, r, arm), o in sorted(d.items()):
        if arm != a:
            continue
        q = d.get((t, r, b))
        if not q or o["rc"] or q["rc"] or not o["turns"] or not q["turns"]:
            continue
        out.append((t, r, o["output_total"], q["output_total"]))
    return out


def exact_perm_p(diffs):
    """Two-sided sign-flip permutation. Exact: 2**n enumerated, not sampled."""
    obs = abs(sum(diffs))
    hit = sum(1 for s in itertools.product((1, -1), repeat=len(diffs))
              if abs(sum(x * y for x, y in zip(s, diffs))) >= obs - 1e-9)
    return hit / 2 ** len(diffs)


def by_task(pairs):
    """Collapse repeats: one proportional delta per task, which is the unit that
    generalises. Four tasks means the floor on a two-sided sign test is 2/2**4."""
    agg = {}
    for t, _, p, q in pairs:
        a, b = agg.setdefault(t, [0, 0])
        agg[t] = [a + p, b + q]
    return {t: (q - p) / p for t, (p, q) in agg.items()}


def report(label, name):
    d = load(name)
    P = paired(d, "plain", "oneline")
    diffs = [p - q for _, _, p, q in P]
    tp, tq = sum(p for _, _, p, _ in P), sum(q for _, _, _, q in P)
    tasks = by_task(P)
    tdiffs = [v for v in tasks.values()]
    print(f"\n=== {label} — one sentence vs no instruction ===")
    print(f"  run-level : n={len(P)} pairs  {tp/len(P):,.0f} -> {tq/len(P):,.0f}  "
          f"{100*(tq-tp)/tp:+.1f}%  lower in {sum(1 for x in diffs if x>0)}/{len(P)}  "
          f"exact p={exact_perm_p(diffs):.4f}")
    print(f"  task-level: n={len(tasks)} tasks  lower in "
          f"{sum(1 for v in tdiffs if v<0)}/{len(tasks)}  "
          f"exact p={exact_perm_p([-v for v in tdiffs]):.4f}  "
          f"(floor for 4 tasks is {2/2**len(tasks):.3f} — this cannot reach 0.05)")
    for t in sorted(tasks):
        print(f"      {t:14s} {100*tasks[t]:+6.1f}%")
    return tasks


def interaction(a_tasks, b_tasks, la, lb):
    """Is the English effect actually smaller, or is that reading two p-values as
    a comparison? Paired on task, on the proportional deltas."""
    keys = sorted(set(a_tasks) & set(b_tasks))
    d = [b_tasks[k] - a_tasks[k] for k in keys]
    print(f"\n=== interaction: does the effect DIFFER between {la} and {lb}? ===")
    for k in keys:
        print(f"  {k:14s} {100*a_tasks[k]:+6.1f}% -> {100*b_tasks[k]:+6.1f}%  "
              f"diff {100*(b_tasks[k]-a_tasks[k]):+6.1f} pp")
    print(f"  mean difference-in-differences: {100*sum(d)/len(d):+.1f} pp, "
          f"exact p={exact_perm_p(d):.4f}, n={len(d)} tasks")
    print("  A non-significant interaction is NOT evidence the effects are equal;")
    print("  with 4 tasks nothing here could reach 0.05. It only says the data do")
    print("  not support claiming one magnitude is larger than the other.")


def gate_negative_control():
    """Round 22, advisor consensus: a gate that scores 48/48 everywhere has not been
    shown to discriminate. Feed it answers it MUST reject."""
    sys.path.insert(0, HERE)
    from rig_confirmatory import T
    print("\n=== substance gate negative control ===")
    bad = {"empty": "", "truncated": "The test fails because", "wrong": "Looks fine to me."}
    ok = True
    for task, spec in sorted(T.items()):
        for label, text in bad.items():
            hits = sum(1 for r in spec["facts"] if re.search(r, text, re.I))
            flag = "PASS" if hits < len(spec["facts"]) else "**GATE FAILED TO REJECT**"
            if hits >= len(spec["facts"]):
                ok = False
            print(f"  {task:14s} {label:10s} {hits}/{len(spec['facts'])} facts  {flag}")
    print(f"  gate rejects degenerate answers: {ok}")
    return ok


if __name__ == "__main__":
    id_t = report("Indonesian", "confirmatory_runs.jsonl")
    en_t = report("English", "english_replication.jsonl")
    interaction(id_t, en_t, "Indonesian", "English")
    assert gate_negative_control(), "substance gate accepted a degenerate answer"
