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
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import carry      # noqa: E402
import extract    # noqa: E402
import msgid      # noqa: E402

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


def rec(mid, blocks, u=None, model="claude-opus-5", msgfields=None, **recfields):
    """One JSONL record: one assistant message identity, the blocks THIS record holds.

    `msgfields` / `recfields` carry the metadata the collision guard reads (message-level
    `stop_reason` and friends; record-level `requestId`). Omitted, they state nothing, and
    a guard must never treat "not stated" as a disagreement."""
    m = {"content": blocks, "model": model}
    if mid is not None:
        m["id"] = mid
    if u is not None:
        m["usage"] = u
    m.update(msgfields or {})
    o = {"type": "assistant", "message": m}
    o.update(recfields)
    return json.dumps(o)


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
        # carry is a REPLAY cost, so an item is indexed by where it entered the FILE, not
        # by which message owns it. The late block of mA was sent after mB existed, so it is
        # replayed from turn 2 on; indexing it at turn 1 would bill it for a turn it was not
        # in the context for. Identity governs turn COUNT and the BILL, not item position.
        check("a late block is indexed where it entered the file, not where its message began",
              sorted((n, i) for (i, n, s_) in items7c if s_ == "prose"),
              [(5, 1), (6, 2), (7, 2)])
        check("the reappearing message is still billed once", u7c["output_tokens"], 3)
        _, _, _, meta7c = carry.scan_full(p7c)
        check("out-of-order records are COUNTED, not assumed away",
              meta7c["out_of_order"], 1)

        # === H1/H2 matrix ====================================================
        # T1..T13. The law is that AMBIGUOUS INPUT MUST NOT BECOME EXACT OUTPUT, and the
        # matrix has to reject both halves of getting that wrong: a build too permissive
        # (merging two messages, resolving a conflicting bill by guessing) and a build too
        # aggressive (rejecting the legitimate multi-record serialisation the corpus is
        # made of). Every fixture below states its metadata explicitly, because "not
        # stated" is the case a guard must never read as a disagreement.
        REQ = "req_01"

        def conflicts(path):
            """-> (kind, counters) for a strict scan: what the ledger refused to guess."""
            try:
                carry.scan_full(path)
            except msgid.Ambiguous as e:
                return e.kind, carry.scan_full(path, strict=False)[3]
            return None, carry.scan_full(path, strict=False)[3]

        # T1 same ID + contiguous multi-block + identical usage => ONE valid message.
        t1 = write(d, "T1.jsonl", [
            rec("t1", [thinking("th")], U_A, msgfields={"stop_reason": "tool_use"}, requestId=REQ),
            rec("t1", [tool("Bash", "x1", {"command": "c"})], U_A,
                msgfields={"stop_reason": "tool_use"}, requestId=REQ),
        ])
        k1, m1 = conflicts(t1)
        check("T1 contiguous multi-block with identical usage is NOT a conflict", k1, None)
        check("T1 is one turn", carry.scan(t1)[0], 1)
        check("T1 is billed once", carry.scan(t1)[2]["output_tokens"], 101)

        # T2 same ID + reappearing legitimate blocks, every guard field agreeing.
        # This is the shape actually in the corpus: one message's records interrupted in
        # FILE ORDER by an unrelated record, same requestId, same usage, same stop_reason.
        t2 = write(d, "T2.jsonl", [
            rec("t2a", [thinking("th")], U_A, msgfields={"stop_reason": "tool_use"}, requestId=REQ),
            rec("t2b", [text("other")], U_B, msgfields={"stop_reason": "end_turn"},
                requestId="req_02"),
            rec("t2a", [tool("Bash", "x2", {"command": "c"})], U_A,
                msgfields={"stop_reason": "tool_use"}, requestId=REQ),
        ])
        k2, m2 = conflicts(t2)
        check("T2 a legitimate reappearance is NOT a collision", k2, None)
        check("T2 the reappearance is COUNTED", m2["out_of_order"], 1)
        check("T2 stays two turns", carry.scan(t2)[0], 2)
        check("T2 identity stays exact", m2["identity_exact"], True)

        # T3 different IDs, otherwise identical metadata and content => two messages.
        t3 = write(d, "T3.jsonl", [
            rec("t3a", [text("same")], usage(5, 5, 5, 5),
                msgfields={"stop_reason": "end_turn"}, requestId=REQ),
            rec("t3b", [text("same")], usage(5, 5, 5, 5),
                msgfields={"stop_reason": "end_turn"}, requestId=REQ),
        ])
        k3, _ = conflicts(t3)
        check("T3 identical metadata under different ids is NOT a conflict", k3, None)
        check("T3 stays two turns", carry.scan(t3)[0], 2)
        check("T3 bills twice", carry.scan(t3)[2]["output_tokens"], 10)

        # T4 same ID + incompatible PROVEN-invariant metadata => MESSAGE_IDENTITY_CONFLICT.
        t4 = write(d, "T4.jsonl", [
            rec("t4", [text("a")], U_A, msgfields={"stop_reason": "tool_use"}, requestId="req_A"),
            rec("t4", [text("b")], U_A, msgfields={"stop_reason": "tool_use"}, requestId="req_B"),
        ])
        k4, m4 = conflicts(t4)
        check("T4 two API requests under one id is MESSAGE_IDENTITY_CONFLICT", k4, "identity")
        check("T4 the collision is counted", m4["identity_conflicts"], 1)
        check("T4 identity is no longer exact", m4["identity_exact"], False)
        check("T4 the usage figure is withheld, not merged",
              carry.scan_full(t4, strict=False)[2].get("output_tokens", 0), 0)
        # ...and on a message-level guard too, not only the record-level one.
        t4b = write(d, "T4b.jsonl", [
            rec("t4b", [text("a")], U_A, msgfields={"stop_reason": "tool_use"}),
            rec("t4b", [text("b")], U_A, msgfields={"stop_reason": "end_turn"}),
        ])
        check("T4b a differing stop_reason is a collision too", conflicts(t4b)[0], "identity")
        t4c = write(d, "T4c.jsonl", [
            rec("t4c", [text("a")], U_A, model="claude-opus-5"),
            rec("t4c", [text("b")], U_A, model="claude-sonnet-5"),
        ])
        check("T4c two models under one id is a collision", conflicts(t4c)[0], "identity")
        # NOT stated is not a disagreement: the guard must not fire on an absent field.
        t4d = write(d, "T4d.jsonl", [
            rec("t4d", [text("a")], U_A, msgfields={"stop_reason": "tool_use"}),
            rec("t4d", [text("b")], U_A),                       # states nothing
            rec("t4d", [text("c")], U_A, requestId=REQ),        # states only requestId
        ])
        check("T4d an absent guard field is NOT a disagreement", conflicts(t4d)[0], None)
        check("T4d stays one turn", carry.scan(t4d)[0], 1)

        # T5 same ID + repeated identical usage => charged once.
        t5 = write(d, "T5.jsonl", [
            rec("t5", [text("a")], usage(7, 7, 7, 7), requestId=REQ),
            rec("t5", [text("b")], usage(7, 7, 7, 7), requestId=REQ),
            rec("t5", [text("c")], usage(7, 7, 7, 7), requestId=REQ),
        ])
        check("T5 repeated identical usage is charged once",
              carry.scan(t5)[2]["output_tokens"], 7)
        check("T5 is no conflict", conflicts(t5)[0], None)

        # T6 usage A then usage B => USAGE_CONFLICT. T7 the same pair reversed.
        t6 = write(d, "T6.jsonl", [
            rec("t6", [text("a")], usage(1, 1, 1, 1), requestId=REQ),
            rec("t6", [text("b")], usage(9, 9, 9, 9), requestId=REQ),
        ])
        k6, m6 = conflicts(t6)
        check("T6 usage A then B is USAGE_CONFLICT", k6, "usage")
        check("T6 the conflict is counted", m6["usage_conflicts"], 1)
        check("T6 identity is untouched by a usage conflict", m6["identity_conflicts"], 0)
        t7 = write(d, "T7.jsonl", [
            rec("t7", [text("a")], usage(9, 9, 9, 9), requestId=REQ),
            rec("t7", [text("b")], usage(1, 1, 1, 1), requestId=REQ),
        ])
        check("T7 usage B then A is USAGE_CONFLICT too (order does not decide)",
              conflicts(t7)[0], "usage")
        # ...and neither ordering may be resolved into a number.
        check("T6 no exact usage survives the conflict",
              sum(carry.scan_full(t6, strict=False)[2].values()), 0)
        check("T7 no exact usage survives the conflict",
              sum(carry.scan_full(t7, strict=False)[2].values()), 0)

        # T8 missing usage then usage A => NOT a conflict; the copy that exists is the bill.
        t8 = write(d, "T8.jsonl", [
            rec("t8", [text("a")], None, requestId=REQ),
            rec("t8", [tool("Bash", "x8", {"command": "c"})], usage(4, 4, 4, 4), requestId=REQ),
        ])
        check("T8 missing-then-present usage is NOT a conflict", conflicts(t8)[0], None)
        check("T8 is one turn", carry.scan(t8)[0], 1)
        check("T8 is billed from the record that has usage",
              carry.scan(t8)[2]["output_tokens"], 4)

        # T9 usage A then missing usage => the same, in the ordering the corpus shows.
        t9 = write(d, "T9.jsonl", [
            rec("t9", [text("a")], usage(4, 4, 4, 4), requestId=REQ),
            rec("t9", [tool("Bash", "x9", {"command": "c"})], None, requestId=REQ),
        ])
        check("T9 present-then-missing usage is NOT a conflict", conflicts(t9)[0], None)
        check("T9 is billed exactly once", carry.scan(t9)[2]["output_tokens"], 4)

        # T10 three or more records where only ONE copy conflicts.
        t10 = write(d, "T10.jsonl", [
            rec("t10", [text("a")], usage(2, 2, 2, 2), requestId=REQ),
            rec("t10", [text("b")], usage(2, 2, 2, 2), requestId=REQ),
            rec("t10", [text("c")], usage(2, 2, 8, 2), requestId=REQ),
        ])
        check("T10 one differing copy among three is USAGE_CONFLICT", conflicts(t10)[0], "usage")

        # T11 legacy / no message.id: the record-level fallback is unchanged.
        check("T11 legacy no-id fallback: one record is one message", carry.scan(p3)[0], 3)
        check("T11 legacy no-id fallback: usage still summed per record",
              carry.scan(p3)[2]["output_tokens"], 3)
        check("T11 legacy no-id records raise nothing", conflicts(p3)[0], None)

        # T12 identity conflict + IDENTICAL usage: the identity path is blocked, and no
        # usage conflict is invented out of it.
        t12 = write(d, "T12.jsonl", [
            rec("t12", [text("a")], U_A, requestId="req_A"),
            rec("t12", [text("b")], U_A, requestId="req_B"),
        ])
        k12, m12 = conflicts(t12)
        check("T12 identity conflict fires", k12, "identity")
        check("T12 does NOT invent a usage conflict", m12["usage_conflicts"], 0)
        check("T12 blocks usage anyway — a merged bill is one bill for two messages",
              m12["usage_exact"], False)

        # T13 valid identity + usage conflict: identity facts stay valid, the bill does not.
        k13, m13 = conflicts(t6)
        check("T13 usage conflict leaves identity exact", m13["identity_exact"], True)
        check("T13 usage conflict blocks the usage-dependent metric", m13["usage_exact"], False)
        check("T13 the turn count, which does not depend on usage, is still right",
              carry.scan_full(t6, strict=False)[0], 1)

        # --- 7d. the conflict must reach the AGGREGATE and the REPORT ----------
        agg = carry.accumulate([t6], min_turns=1)
        check("accumulate aggregates the usage-conflict count", agg["usage_conflicts"], 1)
        check("accumulate counts the conflicted transcript",
              agg["usage_conflicted_transcripts"], 1)
        check("accumulate EXCLUDES it from the exact figures",
              agg["usage_exact_measurement_excluded"], 1)
        check("the excluded source contributes no usage", sum(agg["usage"].values()), 0)
        check("and the report SAYS so rather than keeping it private",
              "USAGE_CONFLICT" in carry.render(agg, markdown=True), True)
        check("and says so in plain-text output too, not only markdown",
              "USAGE_CONFLICT" in carry.render(agg, markdown=False), True)
        check("the report names the exclusion, not just the anomaly",
              "EXCLUDED" in carry.render(agg, markdown=False), True)
        agg4 = carry.accumulate([t4], min_turns=1)
        check("accumulate aggregates the identity-conflict count",
              agg4["identity_conflicts"], 1)
        check("accumulate counts the identity-conflicted transcript",
              agg4["identity_conflicted_transcripts"], 1)
        check("an identity-conflicted source leaves the carry table too",
              agg4["sessions"], 0)
        check("and the report names it MESSAGE_IDENTITY_CONFLICT",
              "MESSAGE_IDENTITY_CONFLICT" in carry.render(agg4, markdown=False), True)
        # A clean corpus must not be poisoned by a conflicted neighbour: the exclusion is
        # per SOURCE, and the sources that determine their own numbers keep them.
        aggmix = carry.accumulate([canonical(d), t6], min_turns=1)
        check("a clean source beside a conflicted one keeps its own bill",
              aggmix["usage"]["output_tokens"], TRUE["output_tokens"])
        check("and the conflicted neighbour is still reported",
              aggmix["usage_exact_measurement_excluded"], 1)

        # --- 7e. PROPAGATION: no consumer may turn a refused bill into a number ---
        # Section 10 of the closure brief, made mechanical. Every module that reads
        # `message.usage` is driven with the SAME conflicting fixtures and must refuse.
        # Reading the source and believing it is not the check; calling it is.
        import importlib                       # noqa: E402  (local to this section)

        def refuses(label, fn, *a, **kw):
            try:
                r = fn(*a, **kw)
                if hasattr(r, "__next__"):     # generators refuse only once drained
                    list(r)
            except msgid.Ambiguous as e:
                check(f"{label} refuses an ambiguous transcript", e.kind is not None, True)
                return
            except Exception as e:             # any other failure is a different bug
                check(f"{label} refuses an ambiguous transcript", f"{type(e).__name__}: {e}",
                      "msgid.Ambiguous")
                return
            check(f"{label} refuses an ambiguous transcript", "returned a number", "Ambiguous")

        EXP = os.path.abspath(os.path.join(HERE, "..", "experiments"))
        for fixture, why in ((t6, "usage conflict"), (t4, "identity conflict")):
            refuses(f"carry.scan ({why})", carry.scan, fixture)
            refuses(f"carry.scan_full ({why})", carry.scan_full, fixture)
            refuses(f"extract.scan ({why})", extract.scan, fixture)
            import bashcost                     # noqa: E402
            import prefix                       # noqa: E402
            import b2t_validate                 # noqa: E402
            refuses(f"bashcost.scan ({why})", bashcost.scan, fixture)
            refuses(f"prefix.turns_with_usage ({why})", prefix.turns_with_usage, fixture)
            refuses(f"b2t_validate.sample ({why})", b2t_validate.sample, fixture)
            sys.path.insert(0, os.path.join(EXP, "truth"))
            try:
                rig_truth = importlib.import_module("rig_truth")
                refuses(f"rig_truth.usage_of ({why})", rig_truth.usage_of, fixture)
            except ImportError as e:
                check(f"rig_truth importable ({why})", str(e), "")
            # price.toks globs a profile root; give it one holding the conflicted fixture.
            sys.path.insert(0, os.path.join(EXP, "skill-ab"))
            price = importlib.import_module("price")
            root = os.path.join(d, "priceroot_" + os.path.basename(fixture))
            os.makedirs(os.path.join(root, price.slug(os.path.join("/w", "fx"))), exist_ok=True)
            open(os.path.join(root, price.slug(os.path.join("/w", "fx")), "t.jsonl"),
                 "w").write(open(fixture).read())
            refuses(f"price.toks ({why})", price.toks, "/w", "fx", (root,))

        # The two rigs that cannot be driven from here (they glob their own run directories)
        # are covered by the property that makes all of the above true: a Ledger is STRICT
        # unless its constructor is told otherwise, and only the one function whose contract
        # is to report and exclude says otherwise. If that stops being true, this fails.
        # A Ledger built non-strict, however it is spelled -- not the string "strict=False"
        # anywhere in a file, which matched an unrelated helper's default argument.
        LOOSE_LEDGER = re.compile(r"Ledger\s*\(\s*(?:strict\s*=\s*)?False")
        allowed = {os.path.join("tools", "carry.py"), os.path.join("tests", "test_multiblock.py")}
        loose = []
        for root, dirs, files in os.walk(os.path.abspath(os.path.join(HERE, ".."))):
            dirs[:] = [x for x in dirs if x not in (".git", "__pycache__")]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                q = os.path.join(root, fn)
                rel = os.path.relpath(q, os.path.abspath(os.path.join(HERE, "..")))
                if rel in allowed or rel.endswith(os.path.join("tools", "msgid.py")):
                    continue
                if LOOSE_LEDGER.search(open(q, encoding="utf-8", errors="replace").read()):
                    loose.append(rel)
        check("no consumer outside carry.accumulate opts out of the strict ledger", loose, [])

        # A conflict must never be filed as a LOSS counter either: "unreadable" says the
        # bytes could not be read, and burying a conflicted source there is the silent
        # discard this whole section exists to prevent.
        real = carry.scan_full
        carry.scan_full = lambda q, **kw: (_ for _ in ()).throw(msgid.Ambiguous("usage"))
        try:
            carry.accumulate([t6], min_turns=1)
            check("accumulate does not swallow Ambiguous into `unreadable`", "swallowed",
                  "raised")
        except msgid.Ambiguous:
            check("accumulate does not swallow Ambiguous into `unreadable`", True, True)
        finally:
            carry.scan_full = real

        # The presentation rig wraps carry.scan: it must publish NOTHING and say why,
        # which is its INFRA_ERROR contract, not a zero it would treat as a measurement.
        sys.path.insert(0, os.path.join(EXP, "presentation"))
        try:
            rig_pres = importlib.import_module("rig_pres")
            m = rig_pres.metrics(t6, "T0", set())
            check("rig_pres publishes no usage for an ambiguous transcript", m["usage"], {})
            check("rig_pres marks the run INFRA_ERROR rather than measuring it",
                  m["transcript_ok"] is False and "scan:" in m.get("infra_reason", ""), True)
        except ImportError as e:
            check("rig_pres importable", str(e), "")

        # --- 8. extract.py agrees with carry.py ------------------------------
        e = extract.scan(canonical(d))
        check("extract.py: N matches the true message count", e["N"], TRUE["turns"])
        check("extract.py and carry.py agree on turn count", e["N"], N)

        # --- 9. mutation oracles ---------------------------------------------
        # The law lives in tools/msgid.py, so that is what gets mutated. Each mutant
        # breaks one half of it and must turn this file RED; a law no mutant can break
        # is a law nothing depends on. M1..M5 cover BOTH failure directions: a build that
        # merges or resolves what it should refuse, and a build that rejects what the
        # corpus legitimately contains.
        TOOLS = os.path.abspath(os.path.join(HERE, "..", "tools"))
        law = open(os.path.join(TOOLS, "msgid.py")).read()
        keep = "    return mid if isinstance(mid, str) and mid else None"
        U_CONFLICT = """                    self.usage_conflicts += 1
                    self._usage_bad.add(mid)
                    if self.strict:
                        raise Ambiguous("usage")"""
        ID_GUARD = """        if bad is None:
            return"""
        REAPPEAR = """            if self._last != mid:
                self.out_of_order += 1   # legitimate: reappearance is COUNTED, not rejected"""
        mutants = {
            # (a) no identity at all -> every record is its own message -> the old bug
            "no_dedup": law.replace(keep, "    return None  # mutant"),
            # (b) one identity for everything -> distinct messages collapse into one
            "over_dedup": law.replace(keep, '    return "CONST"  # mutant'),
            # M1 the usage-conflict detection is gone: a differing copy is simply not seen
            "M1_no_usage_detect": law.replace("                if self._usage[mid] != key:",
                                              "                if False:  # mutant"),
            # M2 the conflict is seen and silently resolved FIRST_WINS
            "M2_first_wins": law.replace(U_CONFLICT, "                    pass  # mutant"),
            # M3 ...and a silent SUM, the same sin with the other sign. A true LAST_WINS
            #    is not reachable from a single-site mutation here, and that is itself a
            #    property of the design: the bill is emitted at the FIRST usage-carrying
            #    record, so no later record can retract it. What a conflicting later copy
            #    CAN do silently is add itself, and that is what this mutant does.
            "M3_silent_sum": law.replace(
                U_CONFLICT,
                "                    self._usage[mid] = key  # mutant\n"
                "                    return t, True"),
            # M4 the detectable identity collision guard is removed
            "M4_no_id_guard": law.replace(ID_GUARD, "        if True:  # mutant\n            return"),
            # M5 TOO AGGRESSIVE: every reappearance is called a collision, which rejects
            #    the legitimate multi-record serialisation the corpus is actually made of
            "M5_reappear_is_collision": law.replace(
                REAPPEAR,
                REAPPEAR + "\n                self.identity_conflicts += 1  # mutant\n"
                           "                if self.strict:\n"
                           '                    raise Ambiguous("identity", "reappearance")'),
        }
        probe_src = (
            "import json, sys\n"
            "sys.path.insert(0, %r)\n" +
            "import carry, msgid\n"
            "out = {}\n"
            "try:\n"
            "    N, items, u = carry.scan(sys.argv[1])\n"
            "    out = {'raised': None, 'N': N, 'out': u['output_tokens']}\n"
            "except msgid.Ambiguous as e:\n"
            "    out = {'raised': e.kind, 'N': None, 'out': None}\n"
            "print(json.dumps(out))\n")

        def run_mutant(name, mutated, target):
            """-> probe dict for `target` under `name`, or None when the mutant is a no-op."""
            if mutated == law:
                check(f"mutant {name} actually changed tools/msgid.py", False, True)
                return None
            md = os.path.join(d, "mut_" + name)
            if not os.path.isdir(md):
                os.makedirs(md, exist_ok=True)
                open(os.path.join(md, "msgid.py"), "w").write(mutated)
                for entry in os.listdir(TOOLS):
                    if entry == "msgid.py":
                        continue
                    link = os.path.join(md, entry)
                    if not os.path.exists(link):
                        os.symlink(os.path.join(TOOLS, entry), link)
                open(os.path.join(md, "probe.py"), "w").write(probe_src % md)
            r = subprocess.run([sys.executable, os.path.join(md, "probe.py"), target],
                               capture_output=True, text=True)
            if r.returncode != 0:
                check(f"mutant {name} runs at all", r.stderr.strip()[-160:], "")
                return None
            return json.loads(r.stdout)

        got = run_mutant("no_dedup", mutants["no_dedup"], p)
        if got:
            check("MUTANT removing identity goes RED (turns)", got["N"] != TRUE["turns"], True)
            check("MUTANT removing identity goes RED (usage)",
                  got["out"] != TRUE["output_tokens"], True)
        got = run_mutant("over_dedup", mutants["over_dedup"], p2)
        if got:
            check("MUTANT collapsing distinct ids goes RED (two ids -> one turn)",
                  got["N"] != 2, True)
        got = run_mutant("over_dedup", mutants["over_dedup"], p)
        if got:
            check("MUTANT collapsing distinct ids under-bills",
                  got["out"] != TRUE["output_tokens"], True)

        # M1..M3 are all judged on ONE fixture with one conflicting usage copy: the honest
        # build refuses it, and each mutant turns it back into an exact number.
        for name, want_out in (("M1_no_usage_detect", 1), ("M2_first_wins", 1),
                               ("M3_silent_sum", 10)):
            got = run_mutant(name, mutants[name], t6)
            if not got:
                continue
            check(f"MUTANT {name} goes RED: a refused bill became an exact number",
                  got["raised"], None)
            check(f"MUTANT {name} is the resolution rule it claims to be",
                  got["out"], want_out)
        check("...and the honest build refuses that same fixture",
              conflicts(t6)[0], "usage")
        # ...and no resolution rule is applied under the hood either: exactly ONE bill is
        # emitted (the first usage-carrying record — a later record cannot retract it), and
        # that one bill is DISQUALIFIED rather than published. This is what makes
        # LAST_WINS / MAX_WINS / MIN_WINS unreachable rather than merely unimplemented.
        led = msgid.Ledger(strict=False)
        bills = [led.bill({"id": "x", "usage": usage(1, 1, 1, 1)}),
                 led.bill({"id": "x", "usage": usage(9, 9, 9, 9)})]
        check("exactly one bill is emitted for a conflicting identity", bills, [True, False])
        check("and that bill is disqualified, not published", led.usage_exact, False)

        got = run_mutant("M4_no_id_guard", mutants["M4_no_id_guard"], t4)
        if got:
            check("MUTANT M4_no_id_guard goes RED: a detectable collision merged silently",
                  got["raised"], None)
            check("MUTANT M4_no_id_guard merged two messages into one turn", got["N"], 1)
        check("...and the honest build refuses that same fixture",
              conflicts(t4)[0], "identity")

        # M5 is the other direction, and it fails against a LEGITIMATE fixture: the
        # too-aggressive build must be caught by the suite just as the too-permissive ones are.
        got = run_mutant("M5_reappear_is_collision", mutants["M5_reappear_is_collision"], t2)
        if got:
            check("MUTANT M5 goes RED: a legitimate reappearance was rejected as a collision",
                  got["raised"], "identity")
        check("...and the honest build accepts that same fixture",
              conflicts(t2)[0], None)

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
