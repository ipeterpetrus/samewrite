#!/usr/bin/env python3
"""Carry per source: who occupies the context, not who writes the most.

carry = size x turns_remaining. The transcript is replayed as cache-read input on
every turn, so an item added at turn i is billed (N - i) more times. This is the
number that decides which rule is worth enforcing; output-token counts are not.

Single pass, no tokenizer (bytes / 3.14, same convention as tools/extract.py), so
it runs over a multi-GB corpus in seconds.

Privacy: reads sizes and tool names only. No path, prompt, file content, or tool
output is stored or printed.

usage: python3 tools/carry.py [transcript.jsonl | profile-dir ...] [--markdown]
                             [--min-turns N]
With no path at all it discovers every Claude Code profile on the machine and says on
stderr which ones it read — a number from one profile reported as "your sessions" is
the quiet error this replaces.
"""
import argparse, collections, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profiles  # multi-profile discovery; see tools/profiles.py

# NOT a universal constant, and this repo no longer applies it silently. Measured with
# tools/b2t_validate.py on the author's own corpus: 3.31 B/token for English text, 1.98 for
# Indonesian — a 1.7x spread, because the tokenizer does not span languages. Shares below are
# immune ((X/K)/(Y/K) = X/Y); absolute token figures are not. So carry is reported in BYTES,
# and a token column appears only when you pass --b2t with a number you measured yourself.
B2T = 1 / 3.14          # chars -> tokens, measured on o200k over this corpus. Sizes here
                        # are len(str), i.e. characters, not UTF-8 bytes; identical for
                        # ASCII, and the constant was calibrated on the same len().


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
    unreadable = short = scanned = 0
    lengths = []
    for p in paths:
        scanned += 1
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
                unreadable=unreadable, short=short, scanned=scanned)


# Relative price of one token in each bucket, base input = 1.0. A bucket's share of the
# BILL is not its share of the VOLUME: cache reads dominate volume at a tenth the price,
# output is a rounding error by volume and double digits by price. Reporting only volume
# sends you optimising the wrong line.
PRICE = {"cache_read_input_tokens": 0.1, "cache_creation_input_tokens": 1.25,
         "output_tokens": 5.0, "input_tokens": 1.0}


def per_turn(a):
    """What one turn actually costs, by bucket. The per-session totals above answer
    'where did the tokens go'; this answers 'what does the next turn cost me', which is
    the number a pruning decision is actually made against."""
    T = a["turns"] or 1
    rows = [(k, v / T, v * PRICE.get(k, 1.0)) for k, v in a["usage"].items() if v]
    P = sum(r[2] for r in rows) or 1
    return [(k, pt, 100 * pw / P) for k, pt, pw in
            sorted(rows, key=lambda r: -r[2])]


def render(a, markdown=False, b2t=None):
    C = sum(a["carry"].values())
    if not C:
        # A silent empty result reads like "your logs are clean". Say which files were
        # skipped and why, so a different transcript shape is visible as a shape problem.
        # "sessions read, carry zero" and "nothing read at all" are different problems and
        # printing one message for both sent a shape mismatch looking like an empty archive.
        return (f"no carry to report: {a['sessions']} session(s) read "
                f"({a.get('short', 0)} below --min-turns, "
                f"{a.get('unreadable', 0)} unreadable). "
                "A session whose every item lands on its final turn carries nothing.\n")
    T, out = a["turns"], []
    med = a["lengths"][len(a["lengths"]) // 2]
    U = sum(a["usage"].values()) or 1
    cr = a["usage"]["cache_read_input_tokens"]
    ot = a["usage"]["output_tokens"]

    if markdown:
        out.append("<!-- generated by tools/carry.py — do not edit by hand -->\n")
        out.append("### Per turn, priced\n")
        out.append("| bucket | tokens per turn | share of price* |")
        out.append("|---|---|---|")
        for k, pt, pw in per_turn(a):
            out.append(f"| `{k}` | {pt:,.0f} | {pw:.1f}% |")
        out.append("\n\\* cache-read 0.1x, cache-write 1.25x, output 5x base input.\n")
        out.append("## Carry by source\n")
        out.append(f"{a['sessions']} sessions, {T:,} turns (median {med}), "
                   f"carry {C:,} bytes"
                   + (f" (~{C * b2t:,.0f} tokens at {1/b2t:.2f} B/tok)" if b2t else "")
                   + "; "
                   f"{a.get('short', 0)} sessions below --min-turns and "
                   f"{a.get('unreadable', 0)} unreadable files skipped. "
                   f"cache_read is {100 * cr / U:.1f}% of billed tokens, output {100 * ot / U:.2f}%.\n")
        out.append("| source | share of carry | bytes/turn |")
        out.append("|---|---|---|")
        for k, v in a["carry"].most_common():
            out.append(f"| `{k}` | {100 * v / C:.2f}% | {a['size'][k] / T:,.0f} |")
        out.append("\nShares are immune to the bytes-per-token constant; absolute token "
                   "figures are not. Measure yours with `tools/b2t_validate.py` and pass "
                   "`--b2t` if you want a token column.")
    else:
        out.append(f"# sessions={a['sessions']} turns={T:,} median_turns={med} "
                   f"carry_bytes={C:,}"
                   + (f" carry_tokens~{C * b2t:,.0f}" if b2t else ""))
        for k, v in a["usage"].most_common():
            out.append(f"  {k:32s} {v:>16,} {100 * v / U:6.2f}%")
        out.append("")
        out.append(f"{'per turn, priced':34s} {'tok/turn':>16s} {'%price':>7s}")
        for k, pt, pw in per_turn(a):
            out.append(f"  {k:32s} {pt:>16,.0f} {pw:>6.1f}%")
        out.append("")
        # %carry SENGAJA di kolom-2. Sebelumnya kolom-2 adalah token; sekarang byte, dan
        # parser posisional lama akan diam-diam melaporkan angka ~3x tanpa satu galat pun.
        # Dengan persen di sana, `int(field2)` melempar — gagal KERAS, bukan salah senyap.
        hdr = f"{'source':34s} {'%carry':>8s} {'carry_B':>16s} {'B/turn':>8s}"
        out.append(hdr + (f" {'carry_tok':>14s}" if b2t else ""))
        for k, v in a["carry"].most_common():
            row = f"{k:34s} {100 * v / C:7.2f}% {v:>16,} {a['size'][k] / T:>8,.0f}"
            out.append(row + (f" {v * b2t:>14,.0f}" if b2t else ""))
        if not b2t:
            out.append("")
            out.append("  carry in BYTES. Shares above are immune to the bytes-per-token "
                       "constant; token figures are not.")
            out.append("  Measure yours: tools/b2t_validate.py — then pass --b2t <bytes-per-token>.")
    return "\n".join(out) + "\n"


def history(path, a, C):
    """Append this run's shares and compare against the previous one.

    An observer that keeps no record can only ever say what today looks like. With a
    history it says what CHANGED, which is the thing a person can act on — and it gets
    sharper every time it runs, because the baseline is real rather than remembered.
    Stores shares and byte counts only: no paths, no filenames, no content.
    """
    now = {"ts": int(time.time()), "sessions": a["sessions"], "turns": a["turns"],
           "carry_bytes": C, "scanned": a.get("scanned", 0),
           "shares": {k: round(100 * v / C, 4) for k, v in a["carry"].most_common()}}
    prev = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:                   # last valid record wins
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if isinstance(o, dict) and isinstance(o.get("shares"), dict):
                    prev = o
    except OSError:
        pass
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(now, ensure_ascii=False) + "\n")
    except OSError:
        pass                                   # observing must not break measuring
    if not prev:
        return ["", f"  history: first record written to {os.path.basename(path)} — "
                    "run again later and this section will show what moved."]
    # Delta hanya berarti kalau KORPUSNYA sebanding. Menjalankan atas satu transkrip lalu
    # atas seluruh arsip menghasilkan selisih belasan poin yang BUKAN pergerakan apa pun —
    # dan tanpa cek ini, "since last run" menyajikannya seolah-olah pergerakan.
    p_scan = prev.get("scanned") or 0
    n_scan = now["scanned"]
    if p_scan and n_scan and (max(p_scan, n_scan) / min(p_scan, n_scan)) > 1.5:
        return ["", f"  corpus changed: {p_scan:,} files scanned last time, {n_scan:,} now.",
                "    Shares are NOT comparable across different inputs — no delta reported.",
                "    Point both runs at the same glob if you want movement."]
    days = (now["ts"] - prev.get("ts", now["ts"])) / 86400.0
    rows = []
    for k, v in now["shares"].items():
        p0 = prev["shares"].get(k)
        if p0 is None:
            rows.append((abs(v), f"  {k:32s} {v:6.2f}%  (new)"))
        elif abs(v - p0) >= 0.05:
            rows.append((abs(v - p0), f"  {k:32s} {p0:6.2f}% -> {v:6.2f}%  ({v - p0:+.2f})"))
    gone = [k for k in prev["shares"] if k not in now["shares"]]
    out = ["", f"  since last run ({days:.1f} days, "
               f"{now['turns'] - prev.get('turns', 0):+,} turns):"]
    if not rows and not gone:
        out.append("    nothing moved by more than 0.05 points.")
    for _, line in sorted(rows, reverse=True)[:8]:
        out.append("  " + line.strip().ljust(0))
    for k in gone[:3]:
        out.append(f"    {k} disappeared")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*",
                    help="transcripts or profile directories; empty = discover all profiles")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--min-turns", type=int, default=50,
                    help="ignore sessions shorter than this (default 50)")
    ap.add_argument("--history", metavar="PATH", default=None,
                    help="append this run's shares to PATH and print what moved since the "
                         "previous run. Shares and counts only — no paths, no content.")
    ap.add_argument("--b2t", type=float, default=None, metavar="BYTES_PER_TOKEN",
                    help="add a token column using YOUR measured ratio (tools/b2t_validate.py). "
                         "Omitted by default: the ratio is language-dependent (3.31 English, "
                         "1.98 Indonesian here) and applying one silently is how every figure "
                         "moves together without anyone noticing.")
    args = ap.parse_args()
    paths, roots = profiles.resolve(args.files)
    line = profiles.note(paths, roots, bool(args.files))
    if line:
        print(line, file=sys.stderr)   # stderr: --markdown output stays pipeable
    a = accumulate(paths, args.min_turns)
    b2t = (1.0 / args.b2t) if args.b2t else None
    sys.stdout.write(render(a, args.markdown, b2t))
    if args.history:
        C = sum(a["carry"].values())
        if C:
            sys.stdout.write("\n".join(history(args.history, a, C)) + "\n")
    # exit non-zero when nothing was recognised: a zero-record run is a schema mismatch,
    # not a finding, and a pipeline must be able to tell the two apart.
    # Exit bukan-nol menandai SCHEMA MISMATCH ("tak ada record dikenali"), bukan "carry nol".
    # Sesi sah yang seluruh isinya jatuh di turn terakhir punya carry 0 dan itu hasil yang
    # benar — meng-exit 2 di sana menyuruh pipeline mengira parsernya rusak.
    return 2 if not a["sessions"] else 0


if __name__ == "__main__":
    sys.exit(main())
