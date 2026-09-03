#!/usr/bin/env python3
"""Carry per source: who occupies the context, not who writes the most.

carry = size x turns_remaining. The transcript is replayed as cache-read input on
every turn, so an item added at turn i is billed (N - i) more times. This is the
number that decides which rule is worth enforcing; output-token counts are not.

Single pass, no tokenizer (bytes / 3.14, same convention as tools/extract.py), so
it runs over a multi-GB corpus in seconds.

Privacy: reads sizes and tool names only. No path, prompt, file content, or tool
output is stored or printed.

usage: python3 tools/carry.py transcript.jsonl [...] [--markdown] [--min-turns N]
"""
import argparse, collections, json, os, sys

B2T = 1 / 3.14          # bytes -> tokens, measured on o200k over this corpus


def scan(path):
    """-> (turns, [(turn, bytes, source)], usage_counter). Sizes only."""
    turn, id2name, items = 0, {}, []
    usage = collections.Counter()
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue

        att = o.get("attachment")
        if isinstance(att, dict):           # hook output, skill listing, reminders
            c = att.get("content")
            if not isinstance(c, str):
                c = json.dumps(c, ensure_ascii=False) if c is not None else ""
            items.append((turn, len(c), "attach:" + str(att.get("type"))))
            continue

        kind, msg = o.get("type"), o.get("message")
        if kind == "assistant" and isinstance(msg, dict):
            u = msg.get("usage") or {}
            if u:
                turn += 1
                for k in ("input_tokens", "output_tokens",
                          "cache_read_input_tokens", "cache_creation_input_tokens"):
                    usage[k] += u.get(k) or 0
            for c in (msg.get("content") or []):
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    items.append((turn, len(c.get("text", "")), "prose"))
                elif c.get("type") == "tool_use":
                    name = c.get("name") or "?"
                    id2name[c.get("id")] = name
                    items.append((turn, len(json.dumps(c.get("input") or {},
                                                       ensure_ascii=False)), "call:" + name))
        elif kind == "user" and isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                items.append((turn, len(content), "human"))
                continue
            for c in (content or []):
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_result":
                    ct = c.get("content")
                    n = len(ct if isinstance(ct, str) else json.dumps(ct, ensure_ascii=False))
                    items.append((turn, n, "result:" + str(id2name.get(c.get("tool_use_id")))))
                elif c.get("type") == "text":
                    items.append((turn, len(c.get("text", "")), "human"))
    return turn, items, usage


def bucket(src):
    """Collapse sources into the buckets a rule can actually target."""
    if src in ("prose", "human") or src.startswith("attach:"):
        return src
    tool = src.split(":", 1)[1] if ":" in src else src
    if tool in ("Bash", "Read"):
        return tool
    if tool in ("Write", "Edit"):
        return "Write/Edit"
    return "other tools"


def accumulate(paths, min_turns=50):
    carry, size, usage = collections.Counter(), collections.Counter(), collections.Counter()
    turns = sessions = 0
    unreadable = short = 0
    lengths = []
    for p in paths:
        try:
            N, items, u = scan(p)
        except OSError:
            unreadable += 1
            continue
        if N < min_turns:                   # stubs and aborted sessions carry nothing
            short += 1
            continue
        sessions += 1
        turns += N
        lengths.append(N)
        usage.update(u)
        for (i, n, src) in items:
            b = bucket(src)
            carry[b] += n * (N - i)
            size[b] += n
    return dict(sessions=sessions, turns=turns, lengths=sorted(lengths),
                carry=carry, size=size, usage=usage,
                unreadable=unreadable, short=short)


def render(a, markdown=False):
    C = sum(a["carry"].values())
    if not C:
        # A silent empty result reads like "your logs are clean". Say which files were
        # skipped and why, so a different transcript shape is visible as a shape problem.
        return ("no session met --min-turns "
                f"({a.get('short', 0)} below threshold, "
                f"{a.get('unreadable', 0)} unreadable)\n")
    T, out = a["turns"], []
    med = a["lengths"][len(a["lengths"]) // 2]
    U = sum(a["usage"].values()) or 1
    cr = a["usage"]["cache_read_input_tokens"]
    ot = a["usage"]["output_tokens"]

    if markdown:
        out.append("<!-- generated by tools/carry.py — do not edit by hand -->\n")
        out.append("## Carry by source\n")
        out.append(f"{a['sessions']} sessions, {T:,} turns (median {med}), "
                   f"carry ~{C * B2T:,.0f} tokens. "
                   f"cache_read is {100 * cr / U:.1f}% of billed tokens, output {100 * ot / U:.2f}%.\n")
        out.append("| source | share of carry | bytes/turn |")
        out.append("|---|---|---|")
        for k, v in a["carry"].most_common():
            out.append(f"| `{k}` | {100 * v / C:.2f}% | {a['size'][k] / T:,.0f} |")
    else:
        out.append(f"# sessions={a['sessions']} turns={T:,} median_turns={med} "
                   f"carry_tokens~{C * B2T:,.0f}")
        for k, v in a["usage"].most_common():
            out.append(f"  {k:32s} {v:>16,} {100 * v / U:6.2f}%")
        out.append("")
        out.append(f"{'source':34s} {'carry_tok':>14s} {'%carry':>8s} {'B/turn':>8s}")
        for k, v in a["carry"].most_common():
            out.append(f"{k:34s} {v * B2T:>14,.0f} {100 * v / C:7.2f}% {a['size'][k] / T:>8,.0f}")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--min-turns", type=int, default=50,
                    help="ignore sessions shorter than this (default 50)")
    args = ap.parse_args()
    a = accumulate(args.files, args.min_turns)
    sys.stdout.write(render(a, args.markdown))
    # exit non-zero when nothing was recognised: a zero-record run is a schema mismatch,
    # not a finding, and a pipeline must be able to tell the two apart.
    return 2 if not sum(a["carry"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
