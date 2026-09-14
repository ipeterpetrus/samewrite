#!/usr/bin/env python3
"""Analisis pilot presentasi — hanya kontras yang dipra-registrasi (PREREGISTRATION.md).

    python3 analyze_pres.py runs/pres1.jsonl [--markdown]
"""
import collections, json, sys

CONTRASTS = [("D", "B", "H1 now vs before"), ("D", "A", "vs bare"), ("D", "C", "H2 vs i-have-adhd full"),
             ("Dh", "D", "H5 one-liner P2"), ("Dm", "D", "H5 one-liner P1"),
             ("E", "D", "H4 +ponytail"), ("F", "D", "H4 +i-have-adhd"), ("F", "C", "stacked vs adhd alone")]


def main(path, md=False):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["arm"]][r["fixture"]] = r
    arms = [a for a in ("A", "B", "C", "D", "Dh", "Dm", "E", "F") if a in by]
    fx = sorted({r["fixture"] for r in rows})
    ok = lambda r: r.get("treatment_ok") and r.get("rc") == 0 and "transcript" in r
    exc = [(r["arm"], r["fixture"]) for r in rows if not ok(r)]
    print(f"{len(rows)} run · {len(arms)} arms · {len(fx)} fixtures · excluded {len(exc)} {exc if exc else ''}")
    hdr = "| arm | ROOT | human_ok | out tok (mean) | last-turn out tok | injected B | pre/clo/decor | state lines | words (mean) |"
    print(hdr if md else hdr.replace("|", " "))
    if md:
        print("|---|---|---|---|---|---|---|---|---|")
    for a in arms:
        rs = [r for r in by[a].values() if ok(r)]
        mean = lambda f: (sum(f(r) for r in rs) / len(rs)) if rs else float("nan")
        root = sum(1 for r in by[a].values() if r["verdict"] == "ROOT")
        hum = sum(1 for r in by[a].values() if r["human_ok"])
        last_out = mean(lambda r: (r["per_turn"][-1]["output_tokens"] if r.get("per_turn") else r["usage"].get("output_tokens", 0)))
        pre = sum(r["classify_last"]["preamble"] for r in rs); clo = sum(r["classify_last"]["closer"] for r in rs)
        dec = sum(r["classify_last"]["decor_steps"] for r in rs); st = sum(r["classify_last"]["state_lines"] for r in rs)
        line = (f"| {a} | {root}/{len(by[a])} | {hum}/{len(by[a])} | {mean(lambda r: r['usage'].get('output_tokens', 0)):,.0f} | "
                f"{last_out:,.0f} | {mean(lambda r: r.get('injected_bytes', 0)):,.0f} | {pre}/{clo}/{dec} | {st} | "
                f"{mean(lambda r: r['classify_last']['words']):,.0f} |")
        print(line if md else line.replace("|", " "))
    print("\nper fixture (verdict/human_ok):")
    for f in fx:
        print("  " + f"{f:16s} " + "  ".join(f"{a}={by[a][f]['verdict'][:4]}/{'ok' if by[a][f]['human_ok'] else 'NO'}" for a in arms if f in by[a]))
    print("\npre-registered contrasts (paired by fixture):")
    for x, y, label in CONTRASTS:
        if x not in by or y not in by:
            continue
        pairs = [f for f in fx if f in by[x] and f in by[y] and ok(by[x][f]) and ok(by[y][f])]
        rx = sum(by[x][f]["verdict"] == "ROOT" for f in pairs); ry = sum(by[y][f]["verdict"] == "ROOT" for f in pairs)
        hx = sum(bool(by[x][f]["human_ok"]) for f in pairs); hy = sum(bool(by[y][f]["human_ok"]) for f in pairs)
        fewer = [f for f in pairs if by[x][f]["usage"].get("output_tokens", 0) < by[y][f]["usage"].get("output_tokens", 0)]
        lost = [f for f in pairs if by[x][f]["verdict"] != "ROOT" and by[y][f]["verdict"] == "ROOT"]
        hlost = [f for f in pairs if not by[x][f]["human_ok"] and by[y][f]["human_ok"]]
        print(f"  {x} vs {y} ({label}): n={len(pairs)} ROOT {rx} vs {ry} · human_ok {hx} vs {hy} · "
              f"{x} fewer output tokens in {len(fewer)}/{len(pairs)}")
        if lost:
            print(f"     correctness LOST by {x}: {', '.join(lost)}")
        if hlost:
            print(f"     human_ok LOST by {x}: {', '.join(hlost)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], "--markdown" in sys.argv))
