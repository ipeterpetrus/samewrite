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
import argparse, collections, json, os, re, sys, time, uuid
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


HISTORY_SCHEMA = 2            # bump when a field's MEANING changes, never for an addition.
                              # 0 = pre-1.2 records with no schema field · 1 = + population identity
                              # 2 = + run_id / scope_id / evidence quality (multi-agent safety)
MAX_LINE = 8 * 1024 * 1024    # a single transcript line larger than this is skipped and COUNTED:
                              # one pathological tool result must not become unbounded memory, and
                              # must not silently shrink the corpus either (evidence goes PARTIAL)
SAFE_LABEL = re.compile(r"[\x00-\x1f\x7f-\x9f]")   # control bytes never belong in a label
MAX_RECORD = 1 << 20          # a history record larger than this is not appended: a partial giant
                              # line is the one shape a concurrent append can actually tear


def samewrite_version():
    """Version of the SameWrite that wrote the record; '' when it cannot be read."""
    try:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         ".claude-plugin", "plugin.json")
        with open(p, encoding="utf-8") as fh:
            return str(json.load(fh).get("version") or "")
    except Exception:
        return ""


def scan(path):
    """-> (turns, [(turn, bytes, source)], usage_counter). Sizes only.

    Thin wrapper over scan_full() so existing callers keep their 3-tuple."""
    turns, items, usage, _meta = scan_full(path)
    return turns, items, usage


def scan_full(path):
    """-> (turns, items, usage, meta). `meta` holds the population identity a later
    comparison needs — which CLI wrote the transcript and which models answered — and
    nothing else: no path, no prompt, no content. Same single pass over the file, so
    the metadata costs one dict lookup per line rather than a second read."""
    turn, id2name, items = 0, {}, []
    usage = collections.Counter()
    runtimes, models = collections.Counter(), collections.Counter()
    oversize = 0
    for line in open(path, errors="replace"):
        if len(line) > MAX_LINE:              # counted, never silently dropped
            oversize += 1
            continue
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue

        v = o.get("version")
        if isinstance(v, str) and v:
            runtimes[v] += 1

        att = o.get("attachment")
        if isinstance(att, dict):           # hook output, skill listing, reminders
            c = att.get("content")
            if not isinstance(c, str):
                c = json.dumps(c, ensure_ascii=False) if c is not None else ""
            items.append((turn, len(c), "attach:" + str(att.get("type"))))
            continue

        kind, msg = o.get("type"), o.get("message")
        if kind == "assistant" and isinstance(msg, dict):
            m = msg.get("model")
            if isinstance(m, str) and m:
                models[m] += 1
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
    return turn, items, usage, {"runtimes": runtimes, "models": models, "oversize": oversize}


def bucket(src):
    """Collapse sources into the buckets a rule can actually target.

    Labels leave this function and go straight to a terminal, a JSON file and a candidate
    specification, and some of them (attachment types) come from the transcript rather than from
    this file. A transcript is untrusted input: control bytes in a label could rewrite a terminal
    line or hide a number. Sanitising here covers every caller at once."""
    src = SAFE_LABEL.sub("", str(src))[:64] or "(unnamed)"
    if src in ("prose", "human") or src.startswith("attach:"):
        return src
    tool = src.split(":", 1)[1] if ":" in src else src
    if tool in ("Bash", "Read"):
        return tool
    if tool in ("Write", "Edit"):
        return "Write/Edit"
    return "other tools"


def accumulate(paths, min_turns=50, max_files=0):
    carry, size, usage = collections.Counter(), collections.Counter(), collections.Counter()
    runtimes, models = collections.Counter(), collections.Counter()
    turns = sessions = 0
    unreadable = short = scanned = oversize = 0
    skipped_by_limit = 0
    total_paths = len(paths)
    lengths = []
    # A bound has to mean "the most RECENT N", not "the first N the filesystem listed". An
    # alphabetical prefix of a long-lived archive is a sample of whatever was created first, which
    # for a 24x7 population is the least informative slice there is.
    if max_files and len(paths) > max_files:
        try:
            paths = sorted(paths, key=lambda q: os.path.getmtime(q), reverse=True)[:max_files]
        except OSError:
            paths = list(paths)[:max_files]
    for p in paths:
        scanned += 1
        try:
            N, items, u, meta = scan_full(p)
        except OSError:
            unreadable += 1
            continue
        except Exception:                      # a transcript that cannot be parsed at all
            unreadable += 1
            continue
        oversize += meta.get("oversize", 0)
        if N < min_turns:                   # stubs and aborted sessions carry nothing
            short += 1
            continue
        sessions += 1
        turns += N
        lengths.append(N)
        usage.update(u)
        runtimes.update(meta["runtimes"])
        models.update(meta["models"])
        for (i, n, src) in items:
            b = bucket(src)
            carry[b] += n * (N - i)
            size[b] += n
    if max_files and scanned >= max_files:
        skipped_by_limit = max(total_paths - max_files, 0)
    # Provenance, not decoration: an analyser that cannot tell a complete sweep from a sweep that
    # hit unreadable files or a file cap will happily call a bounded corpus the population.
    quality = "COMPLETE"
    if unreadable or oversize or skipped_by_limit:
        quality = "PARTIAL"
    if sessions == 0:
        quality = "INVALID" if scanned else "EMPTY"
    return dict(sessions=sessions, turns=turns, lengths=sorted(lengths),
                carry=carry, size=size, usage=usage, runtimes=runtimes, models=models,
                unreadable=unreadable, short=short, scanned=scanned, oversize=oversize,
                skipped_by_limit=skipped_by_limit, quality=quality)


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


def trend(records, key, min_n=4):
    """Arah jangka panjang satu sumber, dan apakah nilai terakhirnya keluar dari kebiasaan.

    Membandingkan dengan record SEBELUMNYA saja hanya bisa bilang "naik sejak kemarin" —
    dua titik tak punya arah. Dengan seluruh berkas: slope per hari (regresi kuadrat
    terkecil atas waktu) dan sebaran historis, jadi lonjakan sesaat bisa dibedakan dari
    pergeseran yang bertahan. Ini bagian yang benar-benar menajam saat berkasnya tumbuh:
    makin banyak titik, makin sempit sebarannya dan makin bermakna slope-nya.
    Mengembalikan None di bawah min_n — arah dari tiga titik adalah tebakan berbaju angka.
    """
    pts = [(r["ts"], r["shares"][key]) for r in records
           if isinstance(r.get("shares"), dict) and key in r["shares"] and r.get("ts")]
    pts.sort()                                  # urutan TULIS bukan urutan WAKTU: jam bisa mundur
    if len(pts) < min_n:
        return None
    t0 = pts[0][0]
    xs = [(t - t0) / 86400.0 for t, _ in pts]      # hari sejak record pertama
    ys = [v for _, v in pts]
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    den = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / den if den else 0.0
    mean = sy / n
    var = sum((y - mean) ** 2 for y in ys) / n
    sd = var ** 0.5
    z = (ys[-1] - mean) / sd if sd > 1e-9 else 0.0
    return {"n": n, "days": xs[-1], "slope": slope, "mean": mean, "sd": sd, "z": z}


def new_run_id():
    """Opaque, collision-resistant, carries nothing about the machine or the user.

    Two agents can legitimately produce the same timestamp, turn count and shares; identity by
    metrics would merge two independent observations into one and undercount the population."""
    return uuid.uuid4().hex


def history(path, a, C, scope_id="default", workload_class=""):
    """Append this run's shares and compare against the previous one.

    An observer that keeps no record can only ever say what today looks like. With a
    history it says what CHANGED, which is the thing a person can act on — and it gets
    sharper every time it runs, because the baseline is real rather than remembered.
    Stores shares and byte counts only: no paths, no filenames, no content.
    """
    T = a["turns"] or 1
    now = {"schema_version": HISTORY_SCHEMA, "samewrite_version": samewrite_version(),
           "record_type": "carry_run", "run_id": new_run_id(),
           # scope = the population this record belongs to. Merging a builder agent's sessions
           # with a reviewer agent's produces a trend neither of them had.
           "scope_id": str(scope_id or "default")[:64],
           "workload_class": str(workload_class or "")[:32],
           "evidence_quality": a.get("quality", "COMPLETE"),
           "unreadable": a.get("unreadable", 0), "oversize": a.get("oversize", 0),
           "skipped_by_limit": a.get("skipped_by_limit", 0),
           "ts": int(time.time()), "sessions": a["sessions"], "turns": a["turns"],
           "carry_bytes": C, "scanned": a.get("scanned", 0),
           # population identity, for comparisons that must not merge different worlds:
           # which CLI wrote the transcripts, which models answered. Counts only.
           "runtimes": dict(a.get("runtimes", {})), "models": dict(a.get("models", {})),
           "shares": {k: round(100 * v / C, 4) for k, v in a["carry"].most_common()},
           # Share berjumlah 100%: satu sumber naik MEMAKSA yang lain turun walau perilaku
           # mereka tak berubah sedikit pun. B/turn tidak terikat konstrain itu, jadi delta
           # share sendirian bisa menceritakan gerakan yang tak pernah terjadi.
           "bpt": {k: round(a["size"][k] / T, 2) for k, _ in a["carry"].most_common()}}
    prev = None
    records = []
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
                    records.append(o)
    except OSError:
        pass
    # Two observers can run at once — the scheduled timer and someone running it by hand.
    # The question is whether their records can interleave mid-line. Measured with strace,
    # not reasoned about: one record of 25,331 bytes leaves as exactly ONE write() of
    # 25,331 bytes. CPython's buffered writer bypasses its own buffer for a payload larger
    # than it, so the size of the record never turns into extra syscalls, and Linux
    # serialises appends to a regular file. An os.write() version was written, measured
    # against this one, and dropped: identical syscall count, so it fixed nothing.
    line = json.dumps(now, ensure_ascii=False) + "\n"
    if len(line.encode("utf-8")) > MAX_RECORD:      # never append what a concurrent writer could tear
        return ["", "  history: record too large to append safely — not written."]
    try:
        with open(path, "a+", encoding="utf-8") as fh:
            # A machine that died mid-append leaves a line with no newline. Appending straight
            # after it would GLUE this record to the fragment and destroy a good record as well
            # as the torn one: two losses from one crash. Cost of the check is one seek.
            #
            # Known, measured, and deliberately left alone: under heavy concurrency this check
            # sometimes inserts a newline that was not needed, leaving one blank line in the file.
            # The kernel extends a file page by page, so another process's in-flight append is
            # briefly visible as a tail with no newline — indistinguishable from a crash fragment
            # at this level. Measured at 64 concurrent writers, 40 rounds each: ~10 rounds show one
            # blank line with this check, ~11 with a binary last-byte version that was written and
            # then discarded for being no better, and 0 with no check at all. So the check is the
            # source, and the effect is cosmetic: every record still lands intact (64 lines, 64
            # parsed, 64 distinct run_ids in every round) and every reader here skips blank lines.
            # Removing the check to remove the blank line would trade a cosmetic artifact for the
            # two-records-lost bug it exists to prevent — tests/test_mutation.py goes RED without
            # it. A version that distinguishes an in-flight append from a dead one needs a second
            # probe, which is real concurrency work and has not been done.
            fh.seek(0, os.SEEK_END)
            if fh.tell():
                fh.seek(fh.tell() - 1)
                if fh.read(1) != "\n":
                    fh.write("\n")
            fh.write(line)
    except OSError:
        pass                                   # observing must not break measuring
    except UnicodeDecodeError:                 # a non-UTF-8 tail: start a fresh line, lose nothing
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n" + line)
        except OSError:
            pass
    if not prev:
        return ["", f"  history: first record written to {os.path.basename(path)} — "
                    "run again later and this section will show what moved."]
    # Delta hanya berarti kalau KORPUSNYA sebanding. Menjalankan atas satu transkrip lalu
    # atas seluruh arsip menghasilkan selisih belasan poin yang BUKAN pergerakan apa pun —
    # dan tanpa cek ini, "since last run" menyajikannya seolah-olah pergerakan.
    # Kriterianya ISI, bukan jumlah berkas. Rotasi log memecah satu transkrip jadi dua
    # tanpa mengubah satu turn pun — memakai jumlah berkas akan menolak perbandingan yang
    # sah. Turn adalah hal yang benar-benar diukur, jadi turn yang menentukan sebanding.
    if str(prev.get("scope_id") or "default") != now["scope_id"]:
        return ["", f"  previous record belongs to scope {prev.get('scope_id') or 'default'!r}, "
                    f"this one to {now['scope_id']!r} — different populations, no delta reported."]
    p_turn = prev.get("turns") or 0
    n_turn = now["turns"] or 0
    if p_turn and n_turn and (max(p_turn, n_turn) / min(p_turn, n_turn)) > 1.5:
        return ["", f"  corpus changed: {p_turn:,} turns last time, {n_turn:,} now "
                    f"({prev.get('scanned', 0):,} -> {now['scanned']:,} files).",
                "    Shares are NOT comparable across different inputs — no delta reported.",
                "    Point both runs at the same glob if you want movement."]
    # Jam mundur: record yang lebih tua tertulis belakangan membuat "since last run" dan
    # slope tren menghitung selisih waktu NEGATIF. Lebih baik diam daripada salah.
    if now["ts"] < (prev.get("ts") or 0):
        return ["", "  clock went backwards since the last record — no delta reported.",
                "    (a record with an older timestamp was appended after a newer one)"]
    days = (now["ts"] - prev.get("ts", now["ts"])) / 86400.0
    rows = []
    for k, v in now["shares"].items():
        p0 = prev["shares"].get(k)
        if p0 is None:
            rows.append((abs(v), f"  {k:32s} {v:6.2f}%  (new)"))
        elif abs(v - p0) >= 0.05:
            b_now = (now.get("bpt") or {}).get(k)
            b_old = (prev.get("bpt") or {}).get(k)
            tail = ""
            if b_now is not None and b_old is not None:
                arrow = "flat" if abs(b_now - b_old) < 0.5 else f"{b_old:,.0f}->{b_now:,.0f} B/turn"
                tail = f"   [{arrow}]"
            rows.append((abs(v - p0),
                         f"  {k:32s} {p0:6.2f}% -> {v:6.2f}%  ({v - p0:+.2f}){tail}"))
    gone = [k for k in prev["shares"] if k not in now["shares"]]
    out = ["", f"  since last run ({days:.1f} days, "
               f"{now['turns'] - prev.get('turns', 0):+,} turns):",
           "    share moves are zero-sum — the [B/turn] tag says whether the source itself",
           "    changed or only its neighbours did."]
    if not rows and not gone:
        out.append("    nothing moved by more than 0.05 points.")
    for _, line in sorted(rows, reverse=True)[:8]:
        out.append("  " + line.strip().ljust(0))
    for k in gone[:3]:
        out.append(f"    {k} disappeared")

    # TREN: butuh seluruh berkas, bukan dua titik terakhir.
    hist = records + [now]
    tr = []
    for k in list(now["shares"])[:12]:
        t = trend(hist, k)
        if not t or t["days"] < 0.5:
            continue
        per_month = t["slope"] * 30
        if abs(per_month) >= 0.2 or abs(t["z"]) >= 2.0:
            tag = "outlier" if abs(t["z"]) >= 2.0 else ""
            tr.append((abs(per_month), f"    {k:30s} {per_month:+6.2f} pts/month"
                                       f"  over {t['n']} runs / {t['days']:.0f}d  {tag}".rstrip()))
    if tr:
        out.append("")
        out.append(f"  trend across {len(hist)} runs (slope of share over time):")
        for _, line in sorted(tr, reverse=True)[:6]:
            out.append(line)
    elif len(hist) < 4:
        out.append("")
        out.append(f"  trend: {len(hist)} run(s) recorded — needs 4 before direction means anything.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*",
                    help="transcripts or profile directories; empty = discover all profiles")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--min-turns", type=int, default=50,
                    help="ignore sessions shorter than this (default 50)")
    ap.add_argument("--scope-id", default="default",
                    help="opaque label for the population this run belongs to (one agent, one role, "
                         "one profile). Records from different scopes are never compared.")
    ap.add_argument("--workload-class", default="",
                    help="optional opaque low-cardinality label; a change in it is a workload shift, "
                         "not a regression")
    ap.add_argument("--max-files", type=int, default=0,
                    help="bounded mode: scan at most N transcripts; the record is marked PARTIAL")
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
    a = accumulate(paths, args.min_turns, max_files=args.max_files)
    b2t = (1.0 / args.b2t) if args.b2t else None
    sys.stdout.write(render(a, args.markdown, b2t))
    if args.history:
        C = sum(a["carry"].values())
        if C:
            sys.stdout.write("\n".join(history(args.history, a, C, scope_id=args.scope_id,
                                                workload_class=args.workload_class)) + "\n")
    # exit non-zero when nothing was recognised: a zero-record run is a schema mismatch,
    # not a finding, and a pipeline must be able to tell the two apart.
    # Exit bukan-nol menandai SCHEMA MISMATCH ("tak ada record dikenali"), bukan "carry nol".
    # Sesi sah yang seluruh isinya jatuh di turn terakhir punya carry 0 dan itu hasil yang
    # benar — meng-exit 2 di sana menyuruh pipeline mengira parsernya rusak.
    return 2 if not a["sessions"] else 0


if __name__ == "__main__":
    sys.exit(main())
