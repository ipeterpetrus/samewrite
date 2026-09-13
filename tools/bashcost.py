#!/usr/bin/env python3
"""Where the Bash line of your carry table actually goes.

carry.py says Bash is the largest source. It does not say which half: the command
text *you* write is billed on every later turn exactly like the output that comes
back. On the author's archive the split was 49/51 — so "truncate tool output" was
half a fix, and the other half was the heredocs in the commands themselves.

Prints aggregates only. Never the command text, never the output, never a path —
the same rule carry.py follows, for the same reason: these transcripts contain
whatever you have ever pasted into a shell.

    python3 tools/bashcost.py ~/.claude/projects/*/*.jsonl
"""
import argparse, collections, hashlib, json, os, statistics, sys

B2T = 1 / 3.14


def nbytes(x):
    """UTF-8 BYTES, not characters. The tables label this column `B`, and `len(str)`
    counts code points — any non-ASCII command, tool result, or schema would be
    reported smaller than it is billed. Non-strings are measured as their JSON form,
    which is what actually travels."""
    if not isinstance(x, str):
        x = json.dumps(x, ensure_ascii=False)
    return len(x.encode("utf-8"))


def scan(path):
    """Return (turns, [(turn_index, command_len, result_len, command_sha)])."""
    pend, rows, N = {}, [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:                        # not .splitlines(): U+2028 is legal here
            # The cheap substring filter used to sit here. It skipped assistant turns that
            # carry no tool block — which silently undercounted N, and N is what --min-turns
            # gates on and what `remaining = N - i` weights every carry number by. Parse
            # every assistant/user line; the filter is only worth it below, per block.
            if '"assistant"' not in line and '"user"' not in line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if not isinstance(o, dict):
                continue
            t, m = o.get("type"), o.get("message")
            if not isinstance(m, dict):
                m = {}
            content = m.get("content")
            if not isinstance(content, list):
                content = []
            if t == "assistant":
                N += 1
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use" \
                            and b.get("name") == "Bash":
                        inp = b.get("input")
                        cmd = (inp or {}).get("command") if isinstance(inp, dict) else None
                        pend[b.get("id")] = (N, cmd if isinstance(cmd, str) else "")
            elif t == "user":
                for b in content:
                    if not isinstance(b, dict) or b.get("type") != "tool_result":
                        continue
                    hit = pend.pop(b.get("tool_use_id"), None)
                    if hit is None:
                        continue
                    i, cmd = hit
                    r = b.get("content")
                    rows.append((i, nbytes(cmd), nbytes(r), cmd))
    return N, rows


def accumulate(paths, min_turns=50):
    calls = []                  # (remaining_turns, cmd_len, res_len)
    heredoc_b = heredoc_n = 0
    dupe = collections.Counter()
    dupe_len = {}
    unreadable = short = 0
    for p in paths:
        try:
            N, rows = scan(p)
        except OSError:
            unreadable += 1
            continue
        if N < min_turns:
            short += 1
            continue
        for i, lc, lr, cmd in rows:
            calls.append((max(N - i, 0), lc, lr))
            if "<<" in cmd:
                heredoc_n += 1
                heredoc_b += lc                      # lc sudah dalam BYTE (nbytes)
                k = hashlib.sha256(cmd.encode()).hexdigest()[:16]
                dupe[k] += 1
                dupe_len[k] = lc
    return dict(calls=calls, heredoc_b=heredoc_b, heredoc_n=heredoc_n,
                dupe=dupe, dupe_len=dupe_len, unreadable=unreadable, short=short)


def render(a):
    calls = a["calls"]
    if not calls:
        return (f"no Bash calls to report ({a['short']} session(s) below the turn "
                f"threshold, {a['unreadable']} unreadable)\n")
    c_cmd = sum(rem * lc for rem, lc, _ in calls)
    c_res = sum(rem * lr for rem, _, lr in calls)
    C = c_cmd + c_res or 1
    res = sorted(lr for _, _, lr in calls)
    out = [f"# {len(calls):,} Bash calls",
           "",
           "## Carry split — both halves are re-sent every later turn",
           f"  command text (you wrote it)  {100 * c_cmd / C:5.1f}%   "
           f"{c_cmd * B2T:>14,.0f} tok-turn",
           f"  result text (it came back)   {100 * c_res / C:5.1f}%   "
           f"{c_res * B2T:>14,.0f} tok-turn",
           ""]
    dup_calls = sum(v - 1 for v in a["dupe"].values() if v > 1)
    dup_b = sum(a["dupe_len"][k] * (v - 1) for k, v in a["dupe"].items() if v > 1)
    out += ["## Heredocs inside those commands",
            f"  {a['heredoc_n']:,} calls, {a['heredoc_b']:,} B "
            f"({100 * a['heredoc_b'] / max(sum(lc for _, lc, _ in calls), 1):.1f}% of command bytes)",
            f"  byte-identical rewrites: {dup_calls:,} calls, {dup_b:,} B — a script "
            f"retyped instead of saved",
            ""]
    med = statistics.median(res)
    out += ["## Result sizes",
            f"  median {med:,.0f} B · p90 {res[int(.90 * len(res))]:,} B · "
            f"p99 {res[int(.99 * len(res))]:,} B · max {res[-1]:,} B", ""]
    out += ["## If every result were truncated at X",
            "| X | result carry left | saved | results touched |",
            "|---|---|---|---|"]
    for X in (10000, 6000, 4000, 2000, 1000):
        new = sum(rem * min(lr, X) for rem, _, lr in calls)
        hit = sum(1 for _, _, lr in calls if lr > X)
        out.append(f"| {X:,} B | {100 * new / (c_res or 1):.1f}% | "
                   f"{100 * (1 - new / (c_res or 1)):.1f}% | "
                   f"{hit:,} ({100 * hit / len(calls):.1f}%) |")
    out += ["",
            "Truncation trades information for tokens: the table is the exchange rate,",
            "not a recommendation. A median result of a few hundred bytes means there is",
            "no fat tail to cut for free."]
    return "\n".join(out) + "\n"


def _selfcheck():
    """One runnable check: carry weights by REMAINING turns, and dupes need 2+."""
    # The fixture must DISTINGUISH remaining-turn weighting from per-call counting.
    # The old one could not: both calls had a 1:2 command/result ratio, so every
    # weighting scheme printed 33.3/66.7 and the assert proved nothing. Here the
    # command is carried 10 turns and the result 1, so per-turn gives 90.9/9.1 while
    # counting calls would give 50/50 — the numbers now move when the weighting does.
    a = dict(calls=[(10, 100, 0), (1, 0, 100)], heredoc_b=0, heredoc_n=0,
             dupe=collections.Counter({"x": 3, "y": 1}), dupe_len={"x": 50, "y": 9},
             unreadable=0, short=0)
    r = render(a)
    assert "90.9%" in r and "9.1%" in r, r
    # and byte counting is UTF-8 bytes, not code points: 'é' is one char, two bytes
    assert nbytes("é") == 2 and nbytes("ok") == 2, nbytes("é")
    assert nbytes({"a": "é"}) == len(json.dumps({"a": "é"}, ensure_ascii=False).encode()), "json path"
    assert "100 B — a script" in r, r            # 50*(3-1) = 100, y (count 1) excluded
    assert render(dict(calls=[], heredoc_b=0, heredoc_n=0, dupe=collections.Counter(),
                       dupe_len={}, unreadable=2, short=3)).startswith("no Bash calls")
    print("selfcheck OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--min-turns", type=int, default=50)
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()
        return 0
    if not args.files:
        ap.error("need transcript files (or --selfcheck)")
    a = accumulate(args.files, args.min_turns)
    sys.stdout.write(render(a))
    return 2 if not a["calls"] else 0


if __name__ == "__main__":
    sys.exit(main())
