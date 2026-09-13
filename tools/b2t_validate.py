#!/usr/bin/env python3
"""Is 3.14 bytes per token still true for YOUR transcripts? It depends on your language.

Every token figure this repo prints is bytes divided by one constant. If that constant is
wrong for your corpus, every absolute number moves with it — and no amount of internal
review catches it, because every layer divides by the same number. This measures it.

Design (the one that survives, after two that did not):
  numerator   = UTF-8 bytes of the assistant's *text* in one turn
  denominator = that turn's `output_tokens`
  controls    = drop turns containing tool_use (tool input is tokenised too) and turns
                with thinking tokens (they inflate the denominator while contributing
                nothing the numerator can see)

Two designs that failed first, kept here so nobody repeats them: dividing total content
bytes by total cache_creation over a session (cache rewrites the prefix every turn, so the
denominator counts repeats the numerator counts once — gave 0.20), and using the first
turn's cache_creation against snapshot bytes (the numerator measures json.dumps of a
structure the vendor tokenises differently — gave 8.14).

    python3 tools/b2t_validate.py ~/.claude/projects/*/*.jsonl
"""
import argparse, glob, json, re, statistics, sys

# Rough language split. Not linguistics — just enough to show the constant is not universal.
ID_MARKERS = re.compile(r"\b(yang|dan|tidak|sudah|dengan|untuk|kalau|bukan)\b")


def sample(path):
    """Yield (bytes_per_token, is_indonesian) for usable assistant turns."""
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return
    with fh:
        for line in fh:                       # not .splitlines(): U+2028 is legal here
            if '"output_tokens"' not in line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if not isinstance(o, dict) or o.get("type") != "assistant":
                continue
            m = o.get("message")
            if not isinstance(m, dict):
                continue
            u = m.get("usage") or {}
            ot = u.get("output_tokens") or 0
            det = u.get("output_tokens_details") or {}
            if det.get("thinking_tokens"):
                continue                      # denominator would count what we cannot see
            c = m.get("content")
            if not isinstance(c, list):
                continue
            if any(isinstance(b, dict) and b.get("type") in ("tool_use", "thinking") for b in c):
                continue
            if ot < 50:
                continue                      # short turns: BPE boundary noise dominates
            txt = "".join(b.get("text", "") for b in c
                          if isinstance(b, dict) and b.get("type") == "text")
            nb = len(txt.encode("utf-8"))
            if nb < 200:
                continue
            yield nb / ot, bool(ID_MARKERS.search(txt))


def render(idn, other):
    out = ["# bytes per output token — measured, not assumed", ""]
    for name, xs in (("Indonesian-marked", idn), ("other (mostly English)", other),
                     ("combined", idn + other)):
        if not xs:
            out.append(f"  {name:24} no sample")
            continue
        xs = sorted(xs)
        out.append(f"  {name:24} n={len(xs):>6,}  median {statistics.median(xs):.2f} B/tok"
                   f"  p25 {xs[len(xs)//4]:.2f}  p75 {xs[3*len(xs)//4]:.2f}")
    allx = idn + other
    if allx:
        m = statistics.median(allx)
        out += ["", f"  repo constant 3.14 -> {100*(m-3.14)/3.14:+.1f}% against your corpus",
                "",
                "  Ratios survive a wrong constant: (X/K)/(Y/K) = X/Y, so shares of carry are",
                "  unaffected. Absolute token figures do not — they move with K, and K is not",
                "  one number across languages."]
    return "\n".join(out) + "\n"


def _selfcheck():
    r = render([2.0, 2.0, 2.0], [3.3, 3.3])
    assert "2.00 B/tok" in r and "3.30 B/tok" in r, r
    assert "Ratios survive" in r, r
    assert render([], []).endswith("no sample\n"), render([], [])
    print("selfcheck OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck()
        return 0
    if not a.files:
        ap.error("need transcript files (or --selfcheck)")
    idn, other = [], []
    for p in a.files:
        for r, is_id in sample(p):
            (idn if is_id else other).append(r)
    sys.stdout.write(render(idn, other))
    return 2 if not (idn or other) else 0


if __name__ == "__main__":
    sys.exit(main())
