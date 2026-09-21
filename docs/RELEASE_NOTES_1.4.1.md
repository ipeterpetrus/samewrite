# SameWrite 1.4.1 — release notes

**One sentence.** The transcript-derived token and turn measurements this repository published
were computed by summing `message.usage` once per JSONL record, and a Claude Code transcript
writes one record per *content block*, so a message that thought, called a tool and wrote prose
was billed three times and counted as three turns; 1.4.1 makes the accounting
message-identity-aware, and makes an accounting it cannot determine refuse to produce a number
at all.

This is a patch release. **The skill body is byte-identical**, its description is unchanged, no
hook behaviour changed, and nothing new is activated. It exists for the measurement, the
regression coverage and the documentation that reconciles the old numbers with the new ones.

## 1. What was wrong

Claude Code writes **one JSONL record per content block** of an assistant message. Every record
of one message repeats that message's `id` and its whole `usage` object. Reported as public
issue [#1](https://github.com/ipeterpetrus/samewrite/issues/1) (roy-tong, 6 Sep 2026),
independently reproduced, and repaired in [#10](https://github.com/ipeterpetrus/samewrite/pull/10).

Two consequences, both real:

- **Usage was billed once per record**, so a multi-record message was billed as many times as
  it had records. Measured on the author's corpus: 1.92 records per message.
- **A turn was counted per record**, inflating the turn count by the same factor — and `carry`
  is `size x turns_remaining`, so the inflation propagated into every carry figure.

Two further defects were then found by adversarial review of the first repair, and are also
closed here: a message whose *first* record carried no usage opened its turn on the second
record, and a message that reappeared after a newer one had opened had its late blocks
attributed to the newer message's turn.

## 2. What changed

- **Accounting is message-identity-aware.** `tools/msgid.py` holds the law: identity is a
  non-empty string `message.id`, a turn is one per identity opened by the FIRST record that
  carries it, usage is billed once per identity, and content blocks are **never** deduplicated
  — the prose block and the tool_use block of one message are two items that both belong to it.
  A record with no usable id is its own message, exactly as before, so legacy and synthetic
  fixtures still mean what they meant.
- **Differing usage for one identity is not resolved.** Not first-wins, not last-wins, not max,
  not min, not sum. No upstream invariant authorises any of those, so the ledger refuses:
  `msgid.Ambiguous` is raised (strict, the default) or counted, and the source is excluded from
  every figure it could contaminate and **reported** as excluded.
- **Detectable identity collisions fail closed.** Six fields were measured to agree on every
  record of one message, with 0 disagreements across 42,793 multi-record identities: `role`,
  `model`, `type`, `stop_reason`, `stop_sequence` and `requestId`. Records sharing an id that
  disagree on one of them are two messages under one id — a `MESSAGE_IDENTITY_CONFLICT`,
  neither merged nor split, with the source excluded and counted. Fields that differ per record
  by design (`uuid`, `parentUuid`, `timestamp`, `apiBlockIndex`) are deliberately **not**
  guards: any one of them would reject every legitimate multi-block message in the corpus.
- **A reappearing identity is not a collision.** `out_of_order` counts it. A mutant that calls
  every reappearance a collision turns the suite RED.
- **No consumer can recreate an exact value from an ambiguous one.** Every module that reads
  `message.usage` is driven in the test suite with the same conflicting fixtures and asserted
  to refuse; a repository-wide assertion keeps any future module from opting out of the strict
  ledger. A conflicted source never enters the evidence manifest and is never filed as
  `unreadable` — that counter means bytes could not be read.
- **Regression and mutation coverage for the real format.** The fixtures are shaped like real
  transcripts (multi-record messages, out-of-order reappearance, usage-less records, oversize
  records, legacy no-id records), and the mutation oracles reject **both** directions: a build
  too permissive, and a build too aggressive.
- **Measurement correction documentation.** `docs/MEASUREMENT_CORRECTION_1_4_1.md` is the
  reproduction, the repair and the re-derivation of every published number that stood on the
  old arithmetic, including the ones that got worse.

## 3. What did NOT change

```text
canonical SKILL.md body ......... byte-identical
frontmatter description ......... unchanged
routing ......................... unchanged
hook behaviour .................. unchanged
MICRO rule ...................... not in this release
filter-loss clause .............. not in this release
failure-signature wording ....... not in this release
new compression ................. none
new memory ...................... none
new hooks ....................... none
new automatic behaviour ......... none
Phase-3 ......................... not resurrected
AI-VOS integration .............. none
```

```text
TOTAL_SAVINGS ................... NOT_PROVEN
WORLD_BEST_CLAIM ................ NOT_TESTED
AUTOMATIC_PROMOTION ............. NO
AUTOMATIC_CANDIDATE_PERSISTENCE . NO
AUTOMATIC_POLICY_MUTATION ....... NO
```

The version bump activates nothing. `tests/test_release_shadow_only.py` proves that
mechanically: no promotion entry point ships, the shadow reporter creates no file and no
candidate, and no runtime module branches on the product version.

## 4. Measurement impact

**The historical inflation is documented, not silently rewritten.** Re-deriving the author's
corpus with message identity reduced the cohort turn count by **48.7%** and the carry total by
**43.9%** against the pre-repair arithmetic. The transcript-derived measurements identified in
`docs/MEASUREMENT_CORRECTION_1_4_1.md` were computed with the old per-record arithmetic; that
document states which of them survive, which move, which are withdrawn, and which are
unaffected by construction.

**What the old arithmetic did and did not touch.** Affected: transcript turn counts,
transcript usage totals, the carry figures derived from those turns, and the experiment cost
and token measurements taken from transcripts. Not affected, and not claimed here to be:
canonical hashes and skill bytes; facts counted per *content block*, since content blocks were
never deduplicated — the overwrite counts and the byte-identical overwrite rate are the same
before and after, while the turn count over the same sample halves; and correctness scores,
which are read from diffs and verdicts rather than from token counts. The per-claim table is
in §5 of the correction document, with an `affected` column stating the verdict for each.

**The H1/H2 hardening on top of that repair changed nothing measurable.** Compared against the
repaired HEAD over a pinned list of 1,390 transcripts whose size and mtime were re-checked
before each run and after the last (0 drifted):

| | before H1/H2 | after H1/H2 |
|---|---|---|
| sessions | 150 | 150 |
| turns | 57,528 | 57,528 |
| input tokens | 20,736,520 | 20,736,520 |
| output tokens | 64,298,630 | 64,298,630 |
| cache-read tokens | 23,337,024,713 | 23,337,024,713 |
| cache-creation tokens | 382,159,149 | 382,159,149 |
| carry bytes | 87,805,884,563 | 87,805,884,563 |
| Bash + Read share of carry | 68.0726% | 68.0726% |
| every per-source share | — | identical |

Unchanged for a stated reason rather than by construction: measured by the shipped ledger over
that list, the **current corpus contains zero detected usage conflicts and zero detected
identity conflicts**, so nothing was excluded. There was nothing to exclude. A corpus that did
hold one would report a different, smaller population — which is the point of the counters.

Also measured on that corpus: 115,558 assistant records, 59,869 distinct ids, 39,289
multi-record identities with usage identical on every record of each, 1 reappearance event, 0
malformed lines, 0 oversize lines.

The bytes-per-token constants are unchanged as well (n=844, median 2.00 B/tok, slope 1.94 over
300 transcripts, before and after).

## 5. Honest source-format limit

This is **not** solved, and 1.4.1 does not claim it is.

    CAN_TWO_DISTINCT_LOGICAL_MESSAGES_REMAIN_STRUCTURALLY_INDISTINGUISHABLE
    FROM_ONE_MULTIBLOCK_MESSAGE = YES

    SOURCE_FORMAT_LIMITATION = YES

The indistinguishable class: two assistant messages sharing one `message.id` on which
**nothing states two different values** — no guard field, and no billed usage counter. That
includes every present-versus-absent case: a `requestId` on one record and not the other (it is
absent on 4,208 records here), and a message that carries usage beside one that carries none,
since missing usage is deliberately not a conflict. Nothing in a transcript separates that from
one message written as several content-block records, because the information is not in the
file.

    UPSTREAM_ASSUMPTION = within one transcript, a non-empty `message.id` identifies exactly
                          one logical assistant message

That assumption is **used, not proven**, and the upstream format is not claimed to guarantee
it. What changed is that it is bounded on both sides: every violation the format can expose is
detected and fails closed, and the part that remains is named here rather than living in a
docstring as a caveat.

One distinction matters and is easy to get backwards: **what is measured at 0 is the
DETECTABLE conflicts.** The indistinguishable class is by construction not observable — if it
could be counted it would not be indistinguishable — so no occurrence count is claimed for it,
in either direction. It has an unknown size and no known instance.

## 6. Compatibility

- **Drop-in patch.** No skill body change, so no model-facing behaviour changes and no
  benchmark is re-run for this release.
- **Evidence history.** Schema 4 is unchanged; records written by 1.4.0 are read exactly as
  before. Nothing in the frozen evidence contract was modified — the conflict counters live
  outside it, and a refused source is reported through the loss counters the contract already
  has, so a 1.4.0 reader evaluates a 1.4.1 record without change.
- **Tool output.** `tools/carry.py` prints the conflict counters only when they are non-zero,
  so a clean corpus produces the same report it did before.
- **Turn counts and token totals will drop** for anyone who recorded numbers with 1.4.0 or
  earlier. That is the repair, not a regression; §4 and the measurement-correction document
  say by how much on the author's corpus, and `tools/carry.py --history` will show the step.
- **Python 3.9 and 3.12**, as before. Standard library only at runtime; `pytest` remains the
  single test-time dependency.

## 7. Canonical body identity

```text
CANONICAL_BODY_SHA256 = 7edec9f21e0bd50583e388e0bdc177f92ba8f0db6ce2bb61acd52b39d81e7767

artifact                FULL_FILE_SHA256   bytes         BODY_SHA256   bytes  desc
CLAUDE (canonical)      d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391
CODEX / AGENTSKILLS     d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391
HERMES                  9cce7a6c367b8b4a    4472    7edec9f21e0bd505    4385     49
OPENCLAW                d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391

CROSS_HOST_BODY_IDENTITY = PASS
```

Identical to 1.4.0. `python3 tools/adapters.py --hashes` recomputes it; `tests/test_adapters.py`
fails if any host's body drifts from the canonical one.

## 8. Install

| host | install |
|---|---|
| **Claude Code** | `claude plugin marketplace add ipeterpetrus/samewrite && claude plugin install samewrite@samewrite` |
| **Codex** | `codex plugin marketplace add ipeterpetrus/samewrite && codex plugin add samewrite@samewrite` |
| **Hermes Agent** | `hermes skills install https://raw.githubusercontent.com/ipeterpetrus/samewrite/v1.4.1/adapters/hermes/samewrite/SKILL.md --yes` |
| **OpenClaw** | `(d=$(mktemp -d) && trap 'rm -rf "$d"' EXIT && curl -fsSL https://github.com/ipeterpetrus/samewrite/archive/refs/tags/v1.4.1.tar.gz \| tar -xz -C "$d" && openclaw skills install "$d"/samewrite-*/skills/samewrite)` |

The raw-URL routes are pinned to the release tag, never to `main`:
`python3 tests/test_install_paths.py` checks offline that the pins name the version this
release actually is.

## Upgrading from 1.4.0

Nothing to migrate. Reinstall by the same route, or bump the plugin through its package
manager. If you kept carry reports produced by 1.4.0 or earlier, re-run `tools/carry.py` before
comparing them with anything produced by 1.4.1 — the old and new arithmetic are not comparable,
and §4 says so with numbers.
