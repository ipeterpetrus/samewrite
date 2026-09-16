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
import argparse, collections, hashlib, json, os, re, sys, time, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profiles  # multi-profile discovery; see tools/profiles.py
import evidence_acquire                        # typed v1.4 producer (frozen constructors)
import evidence_history                        # the history file, read/written through the kernel
from evidence.records import RECORD_SCHEMA_VERSION

# NOT a universal constant, and this repo no longer applies it silently. Measured with
# tools/b2t_validate.py on the author's own corpus: 3.31 B/token for English text, 1.98 for
# Indonesian — a 1.7x spread, because the tokenizer does not span languages. Shares below are
# immune ((X/K)/(Y/K) = X/Y); absolute token figures are not. So carry is reported in BYTES,
# and a token column appears only when you pass --b2t with a number you measured yourself.
B2T = 1 / 3.14          # chars -> tokens, measured on o200k over this corpus. Sizes here
                        # are len(str), i.e. characters, not UTF-8 bytes; identical for
                        # ASCII, and the constant was calibrated on the same len().


HISTORY_SCHEMA = 2            # the generation 1.3 wrote. Kept as the name older callers import.
                              # 0 = pre-1.2 records with no schema field · 1 = + population identity
                              # 2 = + run_id / scope_id / evidence quality (multi-agent safety)
# What this build WRITES. Read from the frozen kernel rather than typed here: the contract owns
# the number, and a second copy of it is how a producer and a reader start disagreeing.
CURRENT_HISTORY_SCHEMA = RECORD_SCHEMA_VERSION
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
    the metadata costs one dict lookup per line rather than a second read.

    The pass also produces `content` — a digest over the bytes this run actually read. The v1.4
    sample manifest answers "did we read the same bytes?", and a digest computed in a second
    pass would answer it about a different read. Reading bytes and decoding per line keeps the
    single pass and makes the digest the true one.
    """
    turn, id2name, items = 0, {}, []
    usage = collections.Counter()
    runtimes, models = collections.Counter(), collections.Counter()
    oversize = malformed = 0
    digest = hashlib.sha256()
    for raw in open(path, "rb"):
        digest.update(raw)
        if len(raw) > MAX_LINE:               # counted, never silently dropped
            oversize += 1
            continue
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            malformed += 1                    # a line this parser could not use, and says so
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
    return turn, items, usage, {"runtimes": runtimes, "models": models, "oversize": oversize,
                                "malformed": malformed, "content": digest.hexdigest()}


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


def _identity(path):
    """The filesystem identity of one source, as the frozen contract identifies it."""
    st = os.stat(path)
    return {"dev": st.st_dev, "inode": st.st_ino, "size": st.st_size,
            "mtime_ns": getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))}


def accumulate(paths, min_turns=50, max_files=0):
    carry, size, usage = collections.Counter(), collections.Counter(), collections.Counter()
    runtimes, models = collections.Counter(), collections.Counter()
    turns = sessions = 0
    unreadable = short = scanned = oversize = 0
    skipped_by_limit = 0
    total_paths = len(paths)
    lengths = []
    # v1.4 evidence: one outcome per selected source, and the identity each source had when it
    # was selected. `sources` is every source attempted; `parsed` is the subset that was read.
    sources, parsed_files = {}, {}
    malformed = identity_changed = empty_source = 0
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
            before = _identity(p)
        except OSError:
            unreadable += 1
            continue
        sources[p] = before
        try:
            N, items, u, meta = scan_full(p)
        except OSError:
            unreadable += 1
            continue
        except Exception:                      # a transcript that cannot be parsed at all
            unreadable += 1
            continue
        try:
            after = _identity(p)
        except OSError:
            unreadable += 1
            continue
        if after != before:
            # The file moved under the read. What was measured is not what was selected, and
            # saying so is the whole point of carrying a source identity.
            identity_changed += 1
            continue
        oversize += meta.get("oversize", 0)
        malformed += meta.get("malformed", 0)
        if N == 0:
            # Read, and it held no turn at all. The contract gives that its OWN outcome, and it
            # is not `parsed`: a source in the manifest is a source something was read FROM, so
            # counting empties as parsed is how a sweep that acquired nothing reads INTACT.
            empty_source += 1
            continue
        parsed_files[p] = {"content": meta["content"], "turns": N}
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
    # The accounting law of the frozen contract: every SELECTED source has exactly one outcome,
    # and selection balances against discovery. `parsed` is len(parsed_files), so the manifest
    # and the counter cannot drift apart.
    # `oversize` and `malformed` here are LINE-level losses inside a transcript, which the
    # certificate carries as `malformed`; its `oversize` counter is a SOURCE skipped for its size
    # and this scan never skips one, so claiming any would be a loss that did not happen.
    selected = total_paths - skipped_by_limit
    accounted = len(parsed_files) + unreadable + identity_changed + empty_source
    counters = {"discovered": total_paths, "skipped_by_limit": skipped_by_limit,
                "unreadable": unreadable, "oversize": 0, "identity_changed": identity_changed,
                "empty_source": empty_source,
                # every selected source the loop did not classify above
                "not_attempted": max(0, selected - accounted),
                "malformed": malformed + oversize, "records_rejected": 0,
                "dirs_unreadable": 0}
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
                skipped_by_limit=skipped_by_limit, quality=quality,
                # v1.4 acquisition facts. `quality` above stays for the 1.3 reader; it is NOT
                # what the new record carries, and no record asserts it.
                sources=sources, parsed=parsed_files, counters=counters,
                sample_bound=max_files or 0, malformed=malformed,
                identity_changed=identity_changed, empty_source=empty_source)


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
    metrics would merge two independent observations into one and undercount the population.

    The spelling is a lowercase version-4 UUID because that is the form the frozen constructor
    `evidence.values.make_run_id` accepts. One spelling, written and validated by the same rule:
    a producer and a decoder that disagree about what an id looks like disagree about what a
    record is.
    """
    return evidence_acquire.new_run_id()


def history(path, a, C, scope_id="default", workload_class="", roots=()):
    """Append this run as a TYPED v1.4 observation and compare against the previous one.

    What changed in v1.4, and why. The record written here is no longer a flat dict this
    function assembles: it is built through the frozen constructors (`tools/evidence_acquire`),
    positioned and chained under a lock (`tools/evidence_history`), and encoded canonically. A
    producer that hand-assembles current-schema JSON is exactly the failure this generation
    exists to remove — the reader would then be checking a shape the writer never had to satisfy.

    What did NOT change: the report. An observer that keeps no record can only ever say what
    today looks like; with a history it says what CHANGED, and both wire generations are read so
    that a machine with 1.3 records still gets its delta. Shares and counts only: no paths, no
    filenames, no content.
    """
    T = a["turns"] or 1
    now = {"schema_version": CURRENT_HISTORY_SCHEMA, "samewrite_version": samewrite_version(),
           "record_type": "carry_sweep", "run_id": evidence_acquire.new_run_id(),
           # scope = the population this record belongs to. Merging a builder agent's sessions
           # with a reviewer agent's produces a trend neither of them had.
           "scope_id": str(scope_id or "default")[:64],
           "workload_class": str(workload_class or "")[:32],
           "ts": int(time.time()), "sessions": a["sessions"], "turns": a["turns"],
           "carry_bytes": C, "scanned": a.get("scanned", 0),
           "shares": ({k: round(100 * v / C, 4) for k, v in a["carry"].most_common()}
                      if C else {}),
           # Share berjumlah 100%: satu sumber naik MEMAKSA yang lain turun walau perilaku
           # mereka tak berubah sedikit pun. B/turn tidak terikat konstrain itu, jadi delta
           # share sendirian bisa menceritakan gerakan yang tak pernah terjadi.
           "bpt": {k: round(a["size"][k] / T, 2) for k, _ in a["carry"].most_common()}}
    records = evidence_history.read_views(path)
    prev = records[-1] if records else None
    # Two observers can run at once — the scheduled timer and someone running it by hand.
    # The question is whether their records can interleave mid-line. Measured with strace,
    # not reasoned about: one record of 25,331 bytes leaves as exactly ONE write() of
    # 25,331 bytes. CPython's buffered writer bypasses its own buffer for a payload larger
    # than it, so the size of the record never turns into extra syscalls, and Linux
    # serialises appends to a regular file. An os.write() version was written, measured
    # against this one, and dropped: identical syscall count, so it fixed nothing.
    written, note = evidence_history.append_chained(
        path, lambda run_seq, prev_digest: evidence_acquire.encoded(
            evidence_acquire.observation(a, now["scope_id"], now["workload_class"],
                                         now["samewrite_version"], run_seq, prev_digest,
                                         now["ts"], run_id=now["run_id"], roots=roots)),
        evidence_acquire.make_scope_id(now["scope_id"]))
    if not written:
        return ["", "  history: %s." % note]
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
        # Unconditional. A sweep that carried nothing is exactly the run whose evidence matters
        # most: with no record, the previous INTACT one keeps standing as the current state, which
        # is the stale-evidence failure the tombstone type exists to stop. Zero carry writes a
        # measurement with no shares; zero sources read writes a tombstone.
        sys.stdout.write("\n".join(history(args.history, a, sum(a["carry"].values()),
                                            scope_id=args.scope_id,
                                            workload_class=args.workload_class,
                                            roots=roots)) + "\n")
    # exit non-zero when nothing was recognised: a zero-record run is a schema mismatch,
    # not a finding, and a pipeline must be able to tell the two apart.
    # Exit bukan-nol menandai SCHEMA MISMATCH ("tak ada record dikenali"), bukan "carry nol".
    # Sesi sah yang seluruh isinya jatuh di turn terakhir punya carry 0 dan itu hasil yang
    # benar — meng-exit 2 di sana menyuruh pipeline mengira parsernya rusak.
    return 2 if not a["sessions"] else 0


if __name__ == "__main__":
    sys.exit(main())
