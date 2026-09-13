#!/usr/bin/env python3
"""The part of every turn that carry.py cannot see: system prompt and tool schemas.

carry.py reads the transcript, so it measures what the transcript contains. The
system prompt and the JSON schema of every tool are sent on every request and
never appear as transcript entries — on this author's machine they are larger
than everything carry.py ranks. They are recoverable: Claude Code records them
once per conversation in a `prompt_snapshot` attachment.

    python3 tools/prefix.py ~/.claude/projects/*/*.jsonl

Prints sizes and tool names. Never a schema, never the prompt text — the system
prompt contains whatever your CLAUDE.md contains.

A tool's schema costs the same whether you call it a thousand times or never.
Cross-check the sizes here against how often you actually used each tool
(tools/skills.py does the same job for skills) before concluding anything.
"""
import argparse, collections, json, os, statistics, sys

B2T = 1 / 3.14


def snapshot(path):
    """First prompt_snapshot carrying real tool definitions, or None."""
    with open(path, encoding="utf-8") as f:
        for line in f:                       # not .splitlines(): U+2028 is legal here
            if "prompt_snapshot" not in line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            a = o.get("attachment") or {}
            if a.get("type") != "prompt_snapshot":
                continue
            t = a.get("tools")
            if isinstance(t, list) and t:
                return t, a.get("systemPrompt")
    return None


def accumulate(paths):
    tools = collections.Counter()            # name -> largest definition seen
    totals, sysb, n = [], [], 0
    for p in paths:
        try:
            hit = snapshot(p)
        except OSError:
            continue
        if not hit:
            continue
        t, sp = hit
        n += 1
        totals.append(len(json.dumps(t, ensure_ascii=False)))
        if sp is not None:
            sysb.append(len(json.dumps(sp, ensure_ascii=False)))
        for x in t:
            if isinstance(x, dict):
                b = len(json.dumps(x, ensure_ascii=False))
                name = x.get("name", "?")
                tools[name] = max(tools[name], b)
    return dict(tools=tools, totals=totals, sysb=sysb, sessions=n)


def render(a):
    if not a["sessions"]:
        return ("no prompt_snapshot found: this archive predates it, or the CLI is not "
                "recording one. Nothing measured — that is not the same as nothing there.\n")
    out = [f"# {a['sessions']} session(s) with a recorded prompt snapshot", ""]
    med = statistics.median(a["totals"])
    out.append(f"  tool schemas : median {med:>9,.0f} B  ~{med * B2T:>8,.0f} tok")
    if a["sysb"]:
        ms = statistics.median(a["sysb"])
        out.append(f"  system prompt: median {ms:>9,.0f} B  ~{ms * B2T:>8,.0f} tok")
        out.append(f"  together     :        {med + ms:>9,.0f} B  ~{(med + ms) * B2T:>8,.0f} tok"
                   f"  — per turn, every turn")
    out += ["", "## Tool schemas — LARGEST definition seen for each, across sessions",
            "## (so these sum to more than one session's total; a schema grows as the",
            "##  CLI ships new options, and the shares below are of this sum, not of a turn)"]
    T = sum(a["tools"].values()) or 1
    for name, b in sorted(a["tools"].items(), key=lambda x: -x[1]):
        out.append(f"  {b:>8,} B  ~{b * B2T:>7,.0f} tok  {100 * b / T:5.1f}%  {name}")
    return "\n".join(out) + "\n"


def _selfcheck():
    a = accumulate([])
    assert render(a).startswith("no prompt_snapshot"), render(a)
    a = dict(tools=collections.Counter({"Big": 3140, "Small": 314}),
             totals=[3454.0], sysb=[314.0], sessions=1)
    r = render(a)
    assert "1,000 tok" in r and "100 tok" in r, r     # 3140/3.14 and 314/3.14
    assert "90.9%" in r, r                            # 3140 of 3454
    assert r.index("Big") < r.index("Small"), "harus urut besar-ke-kecil"
    print("selfcheck OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()
        return 0
    if not args.files:
        ap.error("need transcript files (or --selfcheck)")
    a = accumulate(args.files)
    sys.stdout.write(render(a))
    return 2 if not a["sessions"] else 0


if __name__ == "__main__":
    sys.exit(main())
