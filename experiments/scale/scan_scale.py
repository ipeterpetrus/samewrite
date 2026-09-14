#!/usr/bin/env python3
"""How does the sweep scale, and does it need an incremental index?

A 24x7 agent population does not have 30 transcripts, it has thousands, and they never get
smaller. Two designs were on the table for that: keep an incremental index (remember which files
were already summarised, read only the new ones) or keep the sweep stateless and BOUND it
(`--max-files`, evidence marked PARTIAL). An index is a second piece of persistent state that can
drift, be corrupted, be stale against a rewritten transcript, and has to be invalidated correctly
in every one of those cases — so it is only worth its failure modes if the stateless sweep is
actually too slow.

This measures rather than argues. It builds a synthetic archive at 1k and 10k sessions, sweeps it,
and reports wall time and peak RSS, plus the same sweep bounded to 200 files.

    python3 experiments/scale/scan_scale.py            # 1k and 10k
    python3 experiments/scale/scan_scale.py --quick    # 1k only

Synthetic, local, and thrown away at the end: nothing here reads a real transcript.
"""
import argparse, json, os, resource, shutil, sys, tempfile, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "tools"))
import carry  # noqa: E402

TURNS = 60           # turns per synthetic session — near the real median of the local archive
RESULT = 900         # bytes per tool result


def build(root, n):
    os.makedirs(root, exist_ok=True)
    for s in range(n):
        rows = []
        for i in range(TURNS):
            rows.append({"type": "assistant", "version": "2.1.270", "message": {
                "model": "claude-x", "usage": {"input_tokens": 100, "output_tokens": 20},
                "content": [{"type": "tool_use", "id": f"{s}-{i}", "name": "Bash",
                             "input": {"command": "grep -rn pattern ."}}]}})
            rows.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": f"{s}-{i}", "content": "x" * RESULT}]}})
        with open(os.path.join(root, f"s{s:05d}.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")


def rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1024.0 if sys.platform.startswith("linux") else r / (1024.0 * 1024.0)


def sweep(paths, **kw):
    # ABSOLUTE peak RSS of this process, not a delta: ru_maxrss is a high-water mark, so a delta
    # reads 0.0 whenever an earlier phase already peaked higher and would hide the real ceiling.
    t0 = time.time()
    a = carry.accumulate(paths, min_turns=1, **kw)
    return time.time() - t0, rss_mb(), a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--sizes", type=int, nargs="*", default=None)
    a = ap.parse_args()
    sizes = a.sizes or ([1000] if a.quick else [1000, 10000])

    d = tempfile.mkdtemp(prefix="sw-scale-")
    print(f"{'sessions':>9} {'files MB':>9} {'full s':>8} {'peak RSS MB':>11} "
          f"{'bounded-200 s':>14} {'s / 1k sessions':>16}")
    rows = []
    try:
        for n in sizes:
            root = os.path.join(d, f"a{n}")
            build(root, n)
            paths = sorted(os.path.join(root, f) for f in os.listdir(root))
            mb = sum(os.path.getsize(p) for p in paths) / 1e6
            t_full, rss, acc = sweep(paths)
            t_cap, _, acc_cap = sweep(paths, max_files=200)
            rows.append((n, mb, t_full, rss, t_cap))
            print(f"{n:>9} {mb:>9.1f} {t_full:>8.2f} {rss:>11.1f} {t_cap:>14.2f} "
                  f"{1000 * t_full / n:>16.2f}")
            assert acc["quality"] == "COMPLETE", acc["quality"]
            # A cap only makes evidence PARTIAL when it actually bites; at n <= 200 it does not.
            assert acc_cap["quality"] == ("PARTIAL" if n > 200 else "COMPLETE"), acc_cap["quality"]
            shutil.rmtree(root, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    if len(rows) >= 2:
        (n0, _, t0, _, _), (n1, _, t1, _, _) = rows[0], rows[-1]
        ratio = (t1 / t0) / (n1 / n0)
        print(f"\nscaling: {n0} -> {n1} sessions costs {t1 / t0:.2f}x for {n1 / n0:.0f}x the work "
              f"(ratio {ratio:.2f}; 1.00 = linear, >1 = super-linear)")
    print("\nDecision rule, fixed before the numbers were read: build the incremental index only "
          "if a full sweep of 10k sessions exceeds 120 s or 512 MB RSS. Otherwise keep the sweep "
          "stateless and bound it with --max-files, because a stale or corrupt index is a failure "
          "mode that a stateless sweep simply does not have.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
