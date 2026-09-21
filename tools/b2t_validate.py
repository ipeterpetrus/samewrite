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
import argparse, glob, json, os, re, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import msgid     # one assistant message, however many records carry it

# Rough language split. Not linguistics — just enough to show the constant is not universal.
ID_MARKERS = re.compile(r"\b(yang|dan|tidak|sudah|dengan|untuk|kalau|bukan)\b")


def sample(path):
    """Yield (bytes_per_token, is_indonesian, output_tokens, nbytes) per usable assistant
    MESSAGE.

    Reassembly first, filtering second. Claude Code writes one record per content block,
    and every record of a message repeats that message's `output_tokens`. A message that
    wrote prose AND called a tool therefore has a record that LOOKS text-only while its
    denominator bills the tool JSON too — the exact sample the tool_use control was
    written to drop. Grouping by `message.id` restores the control: a message holding any
    tool_use or thinking block anywhere is dropped, whichever record carried it.

    A record with no usable id is its own message, which keeps synthetic and legacy
    transcripts reading exactly as they did.
    """
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return
    msgs, order = {}, []
    # This function does its OWN grouping (it needs the text blocks, which the Ledger does
    # not carry), so it also does its own first-copy usage pick below -- and that is exactly
    # the silent first-wins the ledger refuses. A strict Ledger fed the same records is the
    # detector: it raises `msgid.Ambiguous` on a usage conflict or an identity collision
    # before any B/token constant is derived from them. It is used for nothing else here,
    # so its turn numbering (this loop skips lines without `output_tokens`) does not matter.
    detector = msgid.Ledger(strict=True)
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
            detector.observe(m, o)
            key = msgid.identity(m)
            if key is None:
                key = ("\x00anon", len(order))   # legacy: one record, one message
            if key not in msgs:
                msgs[key] = {"u": m.get("usage") or {}, "text": [], "drop": False}
                order.append(key)
            r = msgs[key]
            if not r["u"]:
                r["u"] = m.get("usage") or {}
            c = m.get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") in ("tool_use", "thinking"):
                    r["drop"] = True           # same control as before, message-wide now
                elif b.get("type") == "text":
                    r["text"].append(b.get("text", ""))
    for key in order:
        r = msgs[key]
        if r["drop"]:
            continue
        u = r["u"]
        ot = u.get("output_tokens") or 0
        det = u.get("output_tokens_details") or {}
        if det.get("thinking_tokens"):
            continue                          # denominator would count what we cannot see
        if ot < 50:
            continue                          # short turns: BPE boundary noise dominates
        txt = "".join(r["text"])
        nb = len(txt.encode("utf-8"))
        if nb < 200:
            continue
        yield (nb / ot, bool(ID_MARKERS.search(txt)), ot, nb)


def fit(points):
    """Least-squares slope+intercept of bytes ~ tokens.

    Dividing bytes by output_tokens treats the ratio as if every token carried text.
    It does not: each message pays a fixed structural overhead (message boundaries and
    metadata the API counts but the transcript never shows). That overhead inflates the
    denominator, and the shorter the turn the more it distorts — which is why a plain
    median under-reports bytes per token. The slope of the fit is the part that scales
    with content; the intercept is the fixed cost, reported so it can be judged.
    """
    n = len(points)
    if n < 3:
        return None
    sx = sum(t for t, _ in points)
    sy = sum(b for _, b in points)
    sxx = sum(t * t for t, _ in points)
    sxy = sum(t * b for t, b in points)
    den = n * sxx - sx * sx
    if den == 0:
        return None
    slope = (n * sxy - sx * sy) / den
    intercept = (sy - slope * sx) / n
    return slope, intercept


def render(idn, other, pts_i=None, pts_o=None):
    out = ["# bytes per output token — measured, not assumed", ""]
    for name, xs in (("Indonesian-marked", idn), ("other (mostly English)", other),
                     ("combined", idn + other)):
        if not xs:
            out.append(f"  {name:24} no sample")
            continue
        xs = sorted(xs)
        out.append(f"  {name:24} n={len(xs):>6,}  median {statistics.median(xs):.2f} B/tok"
                   f"  p25 {xs[len(xs)//4]:.2f}  p75 {xs[3*len(xs)//4]:.2f}")
    for name, pts in (("Indonesian-marked", pts_i or []), ("other (mostly English)", pts_o or [])):
        f = fit(pts)
        if f:
            out.append(f"  {name:24} fit: {f[0]:.2f} B/tok slope, {f[1]:+,.0f} B intercept"
                       f"  (n={len(pts):,})")
    if pts_i or pts_o:
        out.append("")
        out.append("  The SLOPE is the honest bytes-per-token; the median above is biased low")
        out.append("  because output_tokens also counts per-message structure the text cannot show.")
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
    # slope harus memulihkan rasio sebenarnya walau ada overhead tetap
    f = fit([(100, 100 * 3 + 50), (200, 200 * 3 + 50), (400, 400 * 3 + 50)])
    assert f and abs(f[0] - 3.0) < 1e-6 and abs(f[1] - 50) < 1e-6, f
    assert fit([(1, 1)]) is None, "sampel < 3 tak boleh dipaksakan"
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
    pts_i, pts_o = [], []
    for p in a.files:
        for r, is_id, ot, nb in sample(p):
            (idn if is_id else other).append(r)
            (pts_i if is_id else pts_o).append((ot, nb))
    sys.stdout.write(render(idn, other, pts_i, pts_o))
    return 2 if not (idn or other) else 0


if __name__ == "__main__":
    sys.exit(main())
