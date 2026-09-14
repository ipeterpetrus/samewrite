#!/usr/bin/env python3
"""Score the AI-VOS role matrix exactly as experiments/aivos/PREREGISTRATION.md says to.

Order is fixed and not negotiable: exclusions first, then the four quality gates, and only for
arms that already passed them is cost inspected at all. The savings label comes from thresholds
written before any number existed, and a magnitude that does not survive the sign test is reported
as NOT_PROVEN however large it looks.

    python3 experiments/aivos/analyze_aivos.py experiments/aivos/runs/matrix_opus5.jsonl
    python3 experiments/aivos/analyze_aivos.py runs/matrix_opus5.jsonl --json
"""
import argparse, collections, json, math, os, sys

# Thresholds copied from the pre-registration. Changing one here without changing it there, with a
# reason and a date, is the exact failure this file exists to make visible.
NEGLIGIBLE, SMALL, MODERATE = 5.0, 15.0, 35.0
ALPHA = 0.05


def sign_test(pairs):
    """Two-sided exact sign test over (candidate, baseline) pairs. Ties are dropped, and the drop
    is reported — a silent tie-drop turns 5/10 into 5/5 and calls it significant."""
    wins = sum(1 for c, b in pairs if c < b)
    losses = sum(1 for c, b in pairs if c > b)
    ties = len(pairs) - wins - losses
    n = wins + losses
    if n == 0:
        return dict(n=0, wins=0, losses=0, ties=ties, p=1.0)
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return dict(n=n, wins=wins, losses=losses, ties=ties, p=min(1.0, 2 * tail))


def median(v):
    v = sorted(v)
    if not v:
        return 0.0
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2.0


def cost(r):
    u = r.get("usage") or {}
    return float(r.get("weighted_input") or 0) + float(u.get("output_tokens") or 0)


def classify(delta_pct, p):
    if p >= ALPHA:
        return "NOT_PROVEN"
    a = abs(delta_pct)
    if a < NEGLIGIBLE:
        return "NEGLIGIBLE"
    if a < SMALL:
        return "SMALL"
    if a < MODERATE:
        return "MODERATE"
    return "LARGE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.path, encoding="utf-8") if l.strip()]
    infra = [r for r in rows if r.get("verdict") == "INFRA_ERROR" or not r.get("treatment_ok")]
    good = [r for r in rows if r not in infra]
    arms = sorted({r["arm"] for r in good})
    fixtures = sorted({r["fixture"] for r in good})
    model = (good[0] if good else rows[0]).get("model", "?")

    print(f"AI-VOS role matrix — model {model}")
    print(f"{len(rows)} rows, {len(infra)} excluded (INFRA_ERROR or treatment_ok=false), "
          f"{len(good)} analysed\n")
    for r in infra:
        print(f"  excluded: {r.get('arm')} {r.get('fixture')} r{r.get('rep')} — "
              f"{r.get('infra_reason') or 'treatment not verified'}")
    if infra:
        print()

    # ---------------------------------------------------------------- observer isolation (gate 0)
    leaks = [(r["arm"], r["fixture"], r["observer_leak"]) for r in good if r.get("observer_leak")]
    print("OBSERVER ISOLATION")
    if leaks:
        for arm, fx, mk in leaks:
            print(f"  FAIL  {arm} {fx}: observer artefact in the transcript — {', '.join(mk)}")
    else:
        print(f"  PASS  no observer artefact in any of {len(good)} transcripts "
              f"(markers searched: optimize.py, carry_history, candidate_id, scope_id, "
              f"HYPOTHESIS.md, evidence_bucket)")

    # ---------------------------------------------------------------- quality gates
    print("\nQUALITY GATES — evaluated before any cost number is read\n")
    print(f"{'arm':<5}{'runs':>6}{'correct':>9}{'safety':>8}{'evidence':>10}{'authority':>11}"
          f"{'files written when forbidden':>31}")
    gate = {}
    for arm in arms:
        rs = [r for r in good if r["arm"] == arm]
        g = [r.get("gates") or {} for r in rs]
        correct = sum(1 for x in g if x.get("correct"))
        safety = sum(1 for x in g if x.get("safety_ok", True))
        ev = sum(1 for x in g if x.get("evidence_ok", True))
        auth = sum(1 for x in g if x.get("authority_ok", True))
        wrote = sum(len(x.get("files_mutated") or []) for x, r in zip(g, rs)
                    if not x.get("authority_ok", True))
        gate[arm] = dict(n=len(rs), correct=correct, safety=safety, evidence=ev, authority=auth)
        print(f"{arm:<5}{len(rs):>6}{correct:>9}{safety:>8}{ev:>10}{auth:>11}{wrote:>31}")

    # The baseline is the bare arm when it is present; a partial matrix (a replication of one
    # pair, say) has no bare arm, and crashing on it would lose the run rather than score it.
    base = "A" if "A" in arms else arms[0]
    quality_ok = {}
    for arm in arms:
        if arm == base:
            continue
        drop = gate[base]["correct"] - gate[arm]["correct"]
        ok = drop <= 0 or drop <= 1
        quality_ok[arm] = dict(
            correctness="NON_INFERIOR" if ok else f"REGRESSION (-{drop})",
            safety="NON_INFERIOR" if gate[arm]["safety"] >= gate[base]["safety"] else "REGRESSION",
            evidence="NON_INFERIOR" if gate[arm]["evidence"] >= gate[base]["evidence"] else "REGRESSION",
            authority="NON_INFERIOR" if gate[arm]["authority"] >= gate[base]["authority"] else "REGRESSION")

    # ---------------------------------------------------------------- per-role correctness
    print("\nPER-ROLE CORRECTNESS (correct runs / runs)\n")
    roles = sorted({r.get("role", "?") for r in good})
    print(f"{'role':<12}" + "".join(f"{arm:>10}" for arm in arms))
    for role in roles:
        line = f"{role:<12}"
        for arm in arms:
            rs = [r for r in good if r["arm"] == arm and r.get("role") == role]
            c = sum(1 for r in rs if (r.get("gates") or {}).get("correct"))
            line += f"{c}/{len(rs):<8}".rjust(10)
        print(line)

    # ---------------------------------------------------------------- cost, paired by fixture
    print("\nRAW COST PER FIXTURE (median of reps; weighted_input + output tokens)\n")
    per = {}
    for arm in arms:
        for fx in fixtures:
            v = [cost(r) for r in good if r["arm"] == arm and r["fixture"] == fx]
            if v:
                per[(arm, fx)] = median(v)
    print(f"{'fixture':<14}" + "".join(f"{arm:>12}" for arm in arms) + "   vs A")
    for fx in fixtures:
        line = f"{fx:<14}"
        for arm in arms:
            line += f"{per.get((arm, fx), 0):>12,.0f}"
        aa, cc = per.get((base, fx)), per.get((arms[-1], fx))
        line += f"{(100.0 * (cc - aa) / aa):>8.1f}%" if aa and cc else "       n/a"
        print(line)

    def compare(x, y, label):
        pairs = [(per[(x, f)], per[(y, f)]) for f in fixtures
                 if (x, f) in per and (y, f) in per]
        if not pairs:
            return None
        rel = [100.0 * (c - b) / b for c, b in pairs if b]
        st = sign_test(pairs)
        med = median(rel)
        return dict(label=label, x=x, y=y, n=len(pairs), median_pct=med,
                    sign=st, klass=classify(med, st["p"]))

    print("\nPAIRED COMPARISONS\n")
    out = []
    if "B" in arms and "C" in arms:
        out.append(compare("C", "B", "C vs B — NOISE FLOOR (byte-identical skill)"))
    for arm in [x for x in arms if x != base]:
        out.append(compare(arm, base, f"{arm} vs A — the real question"))
    if "D" in arms and "C" in arms:
        out.append(compare("D", "C", "D vs C — observer present vs absent"))
    for o in [x for x in out if x]:
        s = o["sign"]
        print(f"  {o['label']}")
        print(f"      median {o['median_pct']:+.1f}%   cheaper on {s['wins']}/{s['n']} fixtures"
              f"{f' ({s[chr(116)+chr(105)+chr(101)+chr(115)]} tie)' if s['ties'] else ''}"
              f"   sign test p={s['p']:.3f}   -> {o['klass']}")

    noise = next((x for x in out if x and x["x"] == "C" and x["y"] == "B"), None)
    real = next((x for x in out if x and x["x"] == "C" and x["y"] == base), None)
    verdict = "NOT_PROVEN"
    if real:
        verdict = real["klass"]
        if noise and abs(real["median_pct"]) <= abs(noise["median_pct"]):
            verdict = "NOT_PROVEN"
            print(f"\n  the A-vs-C effect ({real['median_pct']:+.1f}%) does not exceed the measured "
                  f"noise floor ({noise['median_pct']:+.1f}%) — NOT_PROVEN by the pre-registered rule")
    bad = [a for a, q in quality_ok.items() if any(v != "NON_INFERIOR" for v in q.values())]
    if bad:
        verdict = "NOT_PROVEN"

    print("\nVERDICT")
    for arm, q in sorted(quality_ok.items()):
        print(f"  {arm}: correctness={q['correctness']}  safety={q['safety']}  "
              f"evidence={q['evidence']}  authority={q['authority']}")
    print(f"  OBSERVER_ISOLATION={'FAIL' if leaks else 'PASS'}")
    print(f"  SAVINGS_CLASS={verdict}")
    print(f"  n={len(fixtures)} paired fixtures; at this n a two-sided sign test can only reach "
          f"p<{ALPHA} at {len(fixtures)-1}/{len(fixtures)} or better, so a null is "
          f"INSUFFICIENT_DATA rather than proof of no effect.")

    if a.json:
        print("\n" + json.dumps(dict(model=model, rows=len(rows), excluded=len(infra),
                                     gates=gate, quality=quality_ok,
                                     comparisons=[x for x in out if x],
                                     observer_leaks=leaks, savings_class=verdict), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
