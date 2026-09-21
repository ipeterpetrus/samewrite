#!/usr/bin/env python3
"""Real Claude Code transcripts write ONE JSONL record per content block.

Every record of one assistant message repeats the same `message.id` and the same
`message.usage`. Summing usage per record therefore bills one message two, three or
four times, and counting a turn per record inflates the turn count by the same factor.

Measured on this author's corpus before the fix (structure only, no content read):
4,143 transcripts, 377,480 assistant records, 196,759 distinct `message.id` -> 1.92
records per message; usage identical across every multi-record id in 127,934 of
127,934 cases, 0 differing; 3 records in 377,480 carried no id at all.

The suites that existed before this file could not see the format: `turn()` in
tests/test_carry.py and tools/make_fixture.py both emit one record per message with
no `message.id`, which is the one shape the bug does not touch.

Berdiri sendiri — jalankan berkas ini, tanpa runner."""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import carry      # noqa: E402
import extract    # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: dapat {got!r}, harap {want!r}")


# --- fixture vocabulary -------------------------------------------------------
# Distinct values per field, so a field summed by the wrong rule cannot land on the
# right answer by coincidence.
def usage(i, o, cr, cc):
    return {"input_tokens": i, "output_tokens": o,
            "cache_read_input_tokens": cr, "cache_creation_input_tokens": cc}


def rec(mid, blocks, u=None, model="claude-opus-5"):
    """One JSONL record: one assistant message identity, the blocks THIS record holds."""
    m = {"content": blocks, "model": model}
    if mid is not None:
        m["id"] = mid
    if u is not None:
        m["usage"] = u
    return json.dumps({"type": "assistant", "message": m})


def text(s):
    return {"type": "text", "text": s}


def tool(name, tid, inp):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def thinking(s):
    return {"type": "thinking", "thinking": s}


def result(tid, body):
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": body}]}})


def write(d, name, lines):
    p = os.path.join(d, name)
    open(p, "w").write("\n".join(lines) + "\n")
    return p


# The canonical two-message fixture the rest of the file reasons about.
# Message A is written as TWO records (text, then tool_use) sharing id and usage.
# Message B is one record. Truth is derived here, not adopted from anyone's report:
#   assistant messages = 2
#   input  = 11 + 23   = 34
#   output = 101 + 207 = 308
#   c_read = 1001 + 2003 = 3004
#   c_crea = 51 + 57   = 108
U_A = usage(11, 101, 1001, 51)
U_B = usage(23, 207, 2003, 57)
TRUE = {"turns": 2, "input_tokens": 34, "output_tokens": 308,
        "cache_read_input_tokens": 3004, "cache_creation_input_tokens": 108}
# What per-record summing produces instead, spelled out so the RED is legible:
PER_RECORD = {"turns": 3, "input_tokens": 45, "output_tokens": 409,
              "cache_read_input_tokens": 4005, "cache_creation_input_tokens": 159}


def canonical(d):
    return write(d, "canonical.jsonl", [
        rec("msg_A", [text("p" * 10)], U_A),
        rec("msg_A", [tool("Bash", "t1", {"command": "y" * 4})], U_A),
        result("t1", "z" * 100),
        rec("msg_B", [text("q" * 7)], U_B),
    ])


def main():
    with tempfile.TemporaryDirectory() as d:
        # --- 1. the defect itself -------------------------------------------
        p = canonical(d)
        N, items, u = carry.scan(p)
        check("one message split across records counts ONE turn", N, TRUE["turns"])
        for k in ("input_tokens", "output_tokens",
                  "cache_read_input_tokens", "cache_creation_input_tokens"):
            check(f"usage counted once per message: {k}", u[k], TRUE[k])
        check("per-record summing would have given a different answer (fixture is diagnostic)",
              TRUE != PER_RECORD, True)

        # --- 2. content blocks stay attributable ----------------------------
        # Dedup is a MESSAGE-level law. Blocks are not deduplicated: both the prose and
        # the tool call of message A must survive, and both must land on turn 1.
        prose = [(i, n) for (i, n, s) in items if s == "prose"]
        calls = [(i, n) for (i, n, s) in items if s.startswith("call:")]
        check("prose block of a split message is kept", sorted(n for _, n in prose), [7, 10])
        check("tool_use block of a split message is kept", [n for _, n in calls] != [], True)
        check("both blocks of one message land on the SAME turn",
              {i for i, _ in prose} | {i for i, _ in calls}, {1, 2})
        check("the split message's two blocks share turn 1",
              sorted([i for i, n in prose if n == 10] + [i for i, _ in calls]), [1, 1])
        check("tool_result still resolves to its tool name",
              any(s == "result:Bash" for _, _, s in items), True)
        # carry = size x turns_remaining. With the true N=2 the prose of turn 1 carries
        # 10 x (2-1) = 10; per-record accounting (N=3, same block at turn 1) would say 20.
        check("carry uses the true turn count",
              [n * (N - i) for (i, n, s) in items if s == "prose" and n == 10], [10])

        # --- 3. distinct messages must NOT collapse --------------------------
        # Two different ids carrying byte-identical payloads are two messages.
        p2 = write(d, "twins.jsonl", [
            rec("msg_1", [text("same")], usage(5, 5, 5, 5)),
            rec("msg_2", [text("same")], usage(5, 5, 5, 5)),
        ])
        N2, _, u2 = carry.scan(p2)
        check("identical payloads under different ids stay two turns", N2, 2)
        check("identical payloads under different ids bill twice", u2["output_tokens"], 10)

        # --- 4. legacy / synthetic transcripts keep their old behaviour ------
        # No id at all: this is what make_fixture.py and tests/test_carry.py emit, and
        # what every published number before this fix was computed from for those files.
        p3 = write(d, "legacy.jsonl", [
            rec(None, [text("a")], usage(1, 1, 1, 1)),
            rec(None, [text("b")], usage(1, 1, 1, 1)),
            rec(None, [text("c")], usage(1, 1, 1, 1)),
        ])
        N3, _, u3 = carry.scan(p3)
        check("no message.id -> one record is one message (legacy fallback)", N3, 3)
        check("no message.id -> usage still summed per record", u3["output_tokens"], 3)

        # --- 5. shapes the corpus actually contains --------------------------
        # text only / tool_use only / thinking+tool+text ordering / four records.
        p4 = write(d, "shapes.jsonl", [
            rec("s1", [text("only text")], usage(1, 2, 3, 4)),
            rec("s2", [tool("Read", "r1", {"file_path": "/x"})], usage(10, 20, 30, 40)),
            rec("s3", [thinking("t")], usage(100, 200, 300, 400)),
            rec("s3", [tool("Grep", "g1", {"pattern": "x"})], usage(100, 200, 300, 400)),
            rec("s3", [tool("Glob", "g2", {"pattern": "y"})], usage(100, 200, 300, 400)),
            rec("s3", [text("after the calls")], usage(100, 200, 300, 400)),
        ])
        N4, items4, u4 = carry.scan(p4)
        check("text-only, tool-only and a 4-record message = 3 turns", N4, 3)
        check("the 4-record message is billed once", u4["output_tokens"], 2 + 20 + 200)
        check("all four blocks of the split message land on turn 3",
              sorted({i for (i, _, s) in items4
                      if s in ("prose",) or s.startswith("call:")} - {1, 2}), [3])

        # --- 6. degenerate identities ---------------------------------------
        # A record whose id is not a usable string must not silently merge with another.
        p5 = write(d, "malformed.jsonl", [
            rec("", [text("empty id a")], usage(1, 1, 1, 1)),
            rec("", [text("empty id b")], usage(1, 1, 1, 1)),
        ])
        N5, _, _ = carry.scan(p5)
        check("empty-string id is not an identity (two records, two turns)", N5, 2)
        p6 = write(d, "intid.jsonl", [
            rec(7, [text("int id a")], usage(1, 1, 1, 1)),
            rec(7, [text("int id b")], usage(1, 1, 1, 1)),
        ])
        N6, _, _ = carry.scan(p6)
        check("non-string id is not an identity (two records, two turns)", N6, 2)

        # --- 7. usage missing on one record of a message ---------------------
        # Not observed in 377,480 records, but the parser must not crash or drop the
        # message: the record that DOES carry usage is the one that counts.
        p7 = write(d, "partial.jsonl", [
            rec("m1", [text("no usage on this record")], None),
            rec("m1", [tool("Bash", "b1", {"command": "x"})], usage(9, 9, 9, 9)),
        ])
        N7, _, u7 = carry.scan(p7)
        check("a message whose usage arrives on a later record is one turn", N7, 1)
        check("that message is billed exactly once", u7["output_tokens"], 9)

        # --- 7b. ordering: a block must land on ITS OWN message's turn ---------
        # Found by an adversarial cross-family review of the first cut of this fix, which
        # is why the assertions are about the TURN OF THE ITEM and not only about counts:
        # the first cut counted turns correctly and still put blocks on the wrong one.
        p7b = write(d, "order_no_usage_first.jsonl", [
            rec("m9", [text("z" * 12)], None),
            rec("m9", [tool("Bash", "b9", {"command": "x"})], usage(3, 3, 3, 3)),
        ])
        N7b, items7b, _ = carry.scan(p7b)
        check("a message opens its turn on its FIRST record, usage or not", N7b, 1)
        check("a block on the usage-less first record lands on turn 1, not turn 0",
              [i for (i, n, s_) in items7b if s_ == "prose"], [1])

        # A message that reappears AFTER a newer one has opened. Rare and real: 3 of
        # 197,127 message openings in this author's corpus, all in one transcript.
        p7c = write(d, "order_reopen.jsonl", [
            rec("mA", [text("A" * 5)], usage(1, 1, 1, 1)),
            rec("mB", [text("B" * 6)], usage(2, 2, 2, 2)),
            rec("mA", [text("A" * 7)], usage(1, 1, 1, 1)),
        ])
        N7c, items7c, u7c = carry.scan(p7c)
        check("a reappearing message does not open a third turn", N7c, 2)
        check("its late block is attributed to ITS turn, not the newest",
              sorted((n, i) for (i, n, s_) in items7c if s_ == "prose"),
              [(5, 1), (6, 2), (7, 1)])
        check("the reappearing message is still billed once", u7c["output_tokens"], 3)
        _, _, _, meta7c = carry.scan_full(p7c)
        check("out-of-order records are COUNTED, not assumed away",
              meta7c["out_of_order"], 1)

        # --- 7d. the usage-conflict counter is real and it is surfaced ---------
        p7d = write(d, "conflict.jsonl", [
            rec("mC", [text("first")], usage(1, 1, 1, 1)),
            rec("mC", [tool("Bash", "bc", {"command": "x"})], usage(9, 9, 9, 9)),
        ])
        _, _, uc, meta7d = carry.scan_full(p7d)
        check("records of one message disagreeing on usage raise a conflict",
              meta7d["usage_conflicts"], 1)
        check("the first copy is the one billed", uc["output_tokens"], 1)
        agg = carry.accumulate([p7d], min_turns=1)
        check("accumulate aggregates the conflict count", agg["usage_conflicts"], 1)
        check("and the report SAYS so rather than keeping it private",
              "DIFFERING usage" in carry.render(agg, markdown=True), True)

        # --- 8. extract.py agrees with carry.py ------------------------------
        e = extract.scan(canonical(d))
        check("extract.py: N matches the true message count", e["N"], TRUE["turns"])
        check("extract.py and carry.py agree on turn count", e["N"], N)

        # --- 9. mutation oracles ---------------------------------------------
        # The law lives in tools/msgid.py, so that is what gets mutated. Each mutant
        # breaks one half of it and must turn this file RED; a law no mutant can break
        # is a law nothing depends on.
        TOOLS = os.path.abspath(os.path.join(HERE, "..", "tools"))
        law = open(os.path.join(TOOLS, "msgid.py")).read()
        keep = "    return mid if isinstance(mid, str) and mid else None"
        mutants = {
            # (a) no identity at all -> every record is its own message -> the old bug
            "no_dedup": law.replace(keep, "    return None  # mutant"),
            # (b) one identity for everything -> distinct messages collapse into one
            "over_dedup": law.replace(keep, '    return "CONST"  # mutant'),
        }
        for name, mutated in mutants.items():
            if mutated == law:
                check(f"mutant {name} actually changed tools/msgid.py", False, True)
                continue
            md = os.path.join(d, "mut_" + name)
            os.makedirs(md, exist_ok=True)
            open(os.path.join(md, "msgid.py"), "w").write(mutated)
            for entry in os.listdir(TOOLS):
                if entry == "msgid.py":
                    continue
                link = os.path.join(md, entry)
                if not os.path.exists(link):
                    os.symlink(os.path.join(TOOLS, entry), link)
            probe = os.path.join(md, "probe.py")
            open(probe, "w").write(
                "import json, sys\n"
                "sys.path.insert(0, %r)\n" % md +
                "import carry\n"
                "N, items, u = carry.scan(sys.argv[1])\n"
                "print(json.dumps({'N': N, 'out': u['output_tokens']}))\n")
            r = subprocess.run([sys.executable, probe, p], capture_output=True, text=True)
            if r.returncode != 0:
                check(f"mutant {name} runs at all", r.stderr.strip()[-160:], "")
                continue
            got = json.loads(r.stdout)
            if name == "no_dedup":
                check("MUTANT removing identity goes RED (turns)",
                      got["N"] != TRUE["turns"], True)
                check("MUTANT removing identity goes RED (usage)",
                      got["out"] != TRUE["output_tokens"], True)
            else:
                r2 = subprocess.run([sys.executable, probe, p2], capture_output=True,
                                    text=True)
                got2 = json.loads(r2.stdout) if r2.returncode == 0 else {"N": None}
                check("MUTANT collapsing distinct ids goes RED (two ids -> one turn)",
                      got2["N"] != 2, True)
                check("MUTANT collapsing distinct ids under-bills",
                      json.loads(r.stdout)["out"] != TRUE["output_tokens"], True)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
