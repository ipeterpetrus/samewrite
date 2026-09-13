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


# SATUAN, dan kenapa repo ini memakai DUA — dinyatakan, bukan disembunyikan (review ronde-2):
# `carry.py` dan `skills.py` mengukur dengan `len(str)` = CODE POINT, dan konstanta B2T
# (1 tok ~ 3,14 B) dikalibrasi terhadap satuan itu; mengubah penghitungnya tanpa
# mengkalibrasi ulang B2T hanya memindahkan biasnya. Alat yang lebih baru di sini memakai
# UTF-8 BYTE karena itu yang sebenarnya dikirim. Selisihnya DIUKUR di korpus penulis:
# 4.095.770 code point vs 4.134.426 byte = 0,94%. Terlalu kecil untuk menggeser satu pun
# SHARE (semua bucket bergeser searah), cukup besar untuk tidak boleh didiamkan.
def nbytes(obj):
    """UTF-8 BYTES of the JSON form, not code points. Columns here are labelled `B`,
    and a schema full of non-ASCII would otherwise be reported smaller than it is sent."""
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


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
            if not isinstance(o, dict):
                continue
            a = o.get("attachment")
            if not isinstance(a, dict) or a.get("type") != "prompt_snapshot":
                continue
            t = a.get("tools")
            if isinstance(t, list) and t:
                return t, a.get("systemPrompt")
    return None


def accumulate(paths):
    tools = collections.Counter()            # name -> largest definition seen
    totals, sysb, both, n = [], [], [], 0
    for p in paths:
        try:
            hit = snapshot(p)
        except OSError:
            continue
        if not hit:
            continue
        t, sp = hit
        n += 1
        tb = nbytes(t)
        totals.append(tb)
        # T5: only sessions carrying BOTH parts may enter the "together" figure —
        # adding a median over all sessions to a median over a subset is a number
        # that describes no session at all.
        sb = nbytes(sp) if sp is not None else None
        if sb is not None:
            sysb.append(sb)
            both.append(tb + sb)
        for x in t:
            if isinstance(x, dict):
                name = x.get("name", "?")
                if not isinstance(name, str):     # unhashable / odd shapes must not crash
                    name = json.dumps(name, ensure_ascii=False)[:60]
                tools[name] = max(tools[name], nbytes(x))
    return dict(tools=tools, totals=totals, sysb=sysb, both=both, sessions=n)


def render(a):
    if not a["sessions"]:
        return ("no prompt_snapshot found: this archive predates it, or the CLI is not "
                "recording one. Nothing measured — that is not the same as nothing there.\n")
    out = [f"# {a['sessions']} session(s) with a recorded prompt snapshot", ""]
    med = statistics.median(a["totals"])
    out.append(f"  tool schemas : median {med:>9,.0f} B  ~{med * B2T:>8,.0f} tok")
    if a["sysb"]:
        ms = statistics.median(a["sysb"])
        out.append(f"  system prompt: median {ms:>9,.0f} B  ~{ms * B2T:>8,.0f} tok"
                   f"   ({len(a['sysb'])} of {a['sessions']} session(s))")
    # "together" berdiri SENDIRI, di luar cabang system-prompt: kalau tak ada sesi yang
    # membawa kedua bagian, itu fakta yang harus DIKATAKAN, bukan baris yang hilang diam-diam.
    both = a.get("both") or []
    if both:
        mb = statistics.median(both)
        out.append(f"  together     : median {mb:>9,.0f} B  ~{mb * B2T:>8,.0f} tok"
                   f"  — per turn, every turn ({len(both)} session(s) carrying both)")
    else:
        out.append("  together     : not computed — no session carries both parts")
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
             totals=[3454.0], sysb=[314.0], both=[3768.0], sessions=1)
    r = render(a)
    assert "1,000 tok" in r and "100 tok" in r, r     # 3140/3.14 and 314/3.14
    assert "90.9%" in r, r                            # 3140 of 3454
    assert r.index("Big") < r.index("Small"), "harus urut besar-ke-kecil"
    # "together" harus datang dari kohort yang membawa KEDUA bagian, bukan dari
    # penjumlahan dua median atas himpunan sesi berbeda.
    assert "1,200 tok" in r, r                        # 3768/3.14, bukan (3454+314)/3.14 kebetulan
    assert "1 session(s) carrying both" in r, r
    r2 = render(dict(a, sysb=[], both=[]))
    assert "not computed" in r2, r2                   # tanpa pasangan: JANGAN mengarang angka
    # byte = UTF-8, bukan code point
    assert nbytes("é") == len('"é"'.encode("utf-8")), nbytes("é")
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
