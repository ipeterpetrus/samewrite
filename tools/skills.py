#!/usr/bin/env python3
"""Which skills in your skill listing have you never actually used?

The skill listing is one blob injected at turn 0 and carried by every later turn, so
its cost is size x session length whether or not a single entry is ever invoked. This
reads the listing out of your own transcripts, counts every invocation of every entry,
and prices the ones that never fired.

Invocation = a `Skill` tool call, or a `<command-name>` slash invocation. That measures
whether the skill's *body* was ever loaded — nothing more. A never-invoked skill still
had its one-line description sitting in the model's context every turn, and a
description like "use this before proposing a fix" can steer behaviour with no tool call
at all. So this tool prices an entry; it does not tell you whether the entry is doing
something. Removing one is a behaviour change of **unknown sign**: it may free attention
as well as tokens, or it may quietly remove a nudge you were relying on. An adversarial
panel ruled the inference "never invoked, therefore free to remove" PREMISE-BROKEN, and
it was right to.

Claude Code ships its own version of this question: `/skills` lists every entry with
its live token cost and writes the per-skill `skillOverrides` setting for you, and
`/skill-doctor` reports the unused ones where it is enabled. Use those first. This tool
exists because it works over the transcript archive rather than the live session, so it
counts every invocation you have ever made and can be checked against a number the CLI
produces independently — on the author's setup the two agreed within 1.5%.

The settings values, per the CLI's own schema: `name-only` lists the skill without its
description, `user-invocable-only` hides it from the model but keeps `/name` working,
`off` hides it from both, absent means on. For cold skills `user-invocable-only` is
usually the right one: it recovers the whole entry rather than only its description, and
you keep the slash command. Note that a plugin can lock its skills — locked entries can
still be set to `off` or `user-invocable-only`, but not to `name-only`.

Privacy: prints skill names, sizes and counts. No path, prompt, file content, or tool
output is read out.

usage: python3 tools/skills.py transcript.jsonl [...] [--markdown] [--min-uses N]
"""
import argparse, collections, json, os, re, sys

B2T = 1 / 3.14
ENTRY = re.compile(r"^- ([A-Za-z0-9_.:-]+): ")
SLASH = re.compile(r"<command-name>/?([A-Za-z0-9_.:-]+)</command-name>")


def parse_listing(text):
    """-> [(name, bytes)] — a listing entry owns its own line plus its wrapped lines."""
    out, cur = [], None
    for line in text.splitlines(True):
        m = ENTRY.match(line)
        if m:
            if cur:
                out.append(tuple(cur))
            cur = [m.group(1), len(line)]
        elif cur:
            cur[1] += len(line)
    if cur:
        out.append(tuple(cur))
    return out


def scan(paths):
    """-> (largest listing seen, invocation counter, sessions-per-skill)."""
    listing, uses, sess = "", collections.Counter(), collections.defaultdict(set)
    for p in paths:
        try:
            fh = open(p, errors="replace")
        except OSError:
            continue
        for line in fh:
            if ('"skill_listing"' not in line and '"Skill"' not in line
                    and "<command-name>" not in line):
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            att = o.get("attachment")
            if isinstance(att, dict) and att.get("type") == "skill_listing":
                c = att.get("content")
                if isinstance(c, str) and len(c) > len(listing):
                    listing = c            # newest/largest wins: that is what you pay for
                continue
            msg = o.get("message")
            if not isinstance(msg, dict):
                continue
            if o.get("type") == "assistant":
                for c in (msg.get("content") or []):
                    if (isinstance(c, dict) and c.get("type") == "tool_use"
                            and c.get("name") == "Skill"):
                        s = (c.get("input") or {}).get("skill")
                        if s:
                            uses[s] += 1
                            sess[s].add(p)
            elif o.get("type") == "user":
                body = msg.get("content")
                if not isinstance(body, str):
                    body = json.dumps(body, ensure_ascii=False)
                for s in SLASH.findall(body):
                    uses[s] += 1
                    sess[s].add(p)
    return listing, uses, sess


def tally(entries, uses, sess):
    """Count an entry's uses under every name it can be invoked by."""
    rows = []
    for name, size in entries:
        base = name.split(":")[-1]
        keys = {name, base} | {k for k in uses if k.endswith(":" + base)}
        n = sum(uses.get(k, 0) for k in keys)
        s = set()
        for k in keys:
            s |= sess.get(k, set())
        rows.append((name, size, n, len(s)))
    return sorted(rows, key=lambda r: (r[2], -r[1]))


def render(listing, rows, min_uses, markdown):
    total = sum(r[1] for r in rows)
    cold = [r for r in rows if r[2] <= min_uses]
    cold_b = sum(r[1] for r in cold)
    share = 100 * cold_b / total if total else 0
    out = []
    if markdown:
        out.append("<!-- generated by tools/skills.py — do not edit by hand -->\n")
        out.append("## Skill listing\n")
        out.append(f"Listing is **{len(listing):,} bytes**, injected at turn 0 and carried "
                   f"by every later turn. {len(cold)} of {len(rows)} entries were invoked "
                   f"{min_uses} time(s) or fewer: **{cold_b:,} bytes, {share:.1f}% of the "
                   f"listing** (~{cold_b * B2T:,.0f} tokens per turn of every session).\n")
        out.append("| skill | bytes | uses | sessions |")
        out.append("|---|---|---|---|")
        for name, size, n, s in rows:
            out.append(f"| `{name}` | {size:,} | {n:,} | {s:,} |")
    else:
        out.append(f"listing {len(listing):,} B · {len(rows)} entries · "
                   f"{sum(r[2] for r in rows):,} invocations")
        out.append(f"{'skill':46s} {'bytes':>7s} {'uses':>6s} {'sessions':>9s}")
        for name, size, n, s in rows:
            out.append(f"{name[:46]:46s} {size:>7,} {n:>6,} {s:>9,}")
        out.append("")
        out.append(f"invoked <={min_uses}: {len(cold)}/{len(rows)} entries · {cold_b:,} B "
                   f"= {share:.1f}% of the listing (~{cold_b * B2T:,.0f} tokens, every turn)")
        out.append("act on it: settings `skillOverrides` "
                   "(on | name-only | user-invocable-only | off), or the /settings panel")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--min-uses", type=int, default=0,
                    help="treat entries with this many uses or fewer as cold (default 0)")
    args = ap.parse_args()
    listing, uses, sess = scan(args.files)
    if not listing:
        print("no skill listing found in these transcripts — nothing to price")
        return 1
    rows = tally(parse_listing(listing), uses, sess)
    sys.stdout.write(render(listing, rows, args.min_uses, args.markdown))
    return 0


if __name__ == "__main__":
    sys.exit(main())
