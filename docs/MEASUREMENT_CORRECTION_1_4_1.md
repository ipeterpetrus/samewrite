# Measurement correction — v1.4.1

Public issue [#1](https://github.com/ipeterpetrus/samewrite/issues/1) (roy-tong, 6 Sep 2026)
reported that `tools/carry.py`, `tools/extract.py` and `experiments/skill-ab/price.py` sum
`message.usage` once per JSONL record. This document is the independent reproduction, the
repair, and the re-derivation of every published number that stood on the old arithmetic.

Nothing here was taken on the reporter's word, or on any model's. Every number below was
produced by running the two accountings over the same files in the same process.

## 1. What the transcripts actually contain

Claude Code writes **one JSONL record per content block** of an assistant message. Every
record of one message repeats that message's `id` and its whole `usage` object. Measured on
this author's corpus, structure only — record type, `message.id`, `message.usage`, block
types; no prompt, no tool input, no file content was read:

| | |
|---|---|
| transcripts scanned | 4,143 |
| assistant records | 377,648 |
| distinct `message.id` | 196,759 |
| records per message | **1.92** |
| messages spanning >1 record | 127,934 |
| of those, usage **identical** on every record | **127,934 (100%)**, 0 differing, 0 partial |
| records carrying no usable id | 3 |
| records carrying no usage | 0 |
| records holding exactly one content block | 377,441 of 377,480 sampled |

Span histogram: 68,825 messages of 1 record, 82,428 of 2, 40,988 of 3, 2,832 of 4, and a
tail to 11.

So the format claim in the issue is correct, and the usage-selection question it did not
ask has an answer: the copies are not provisional-then-final, they are identical.

## 2. The law, and why the fixtures could not see the bug

`tools/msgid.py` now holds one accounting law that every consumer calls:

- **identity** — `message.id` when it is a non-empty string; otherwise the record is its own
  message. `tools/make_fixture.py` and the `turn()` helper in `tests/test_carry.py` both emit
  one record per message with **no** `message.id`, which is the one shape the bug cannot
  touch. That is why 1,037 assertions were green over a defect this large, and why the
  fallback is kept rather than removed: it is what makes those fixtures still mean what they
  meant.
- **turn** — one per identity, opened by the **first record that carries the identity**,
  whether or not that record carries usage. Every block of the message belongs to that turn,
  including a block on a record that arrives before the usage does, and including a record of
  an older message that reappears after a newer one has opened.
- **usage** — billed once per identity, from the first record that carries it. All observed
  copies are identical, so first and last are the same number today; `usage_conflicts` counts
  the day that stops being true instead of silently picking a winner.
- **blocks** — *not* deduplicated. Identity is a message-level law. The prose block and the
  tool_use block of one message remain two items, and both belong to that message's turn.

`tests/test_multiblock.py` (39 assertions) pins all four, including two mutation oracles: an
identity function that returns `None` (dedup removed) and one that returns a constant
(distinct messages collapsed) must each turn the suite red.

### The two assumptions, counted rather than believed

`usage_conflicts` counts a message whose records disagree on usage. `out_of_order` counts a
message whose records are not adjacent. `carry.accumulate` aggregates both and
`carry.render` prints them — including on the empty-carry path, because a transcript that
broke the law still broke it when the carry total happened to be zero. Over the 50+ cohort of
this host: **usage_conflicts = 0, out_of_order = 1**.

This does not make the law safe against everything. Two genuinely different messages that
shared one `message.id` would merge here and no transcript could tell that apart from one
message written twice. The law assumes vendor ids identify a message; what it does not do is
assume it silently.

### What an adversarial review changed

The first cut of this fix counted turns correctly and still attributed blocks to the wrong
turn in two shapes, both found by a cross-family review that was asked to break it rather
than approve it:

- a message whose **first record carried no usage** opened its turn on the second record, so
  the first record's blocks were attributed to the previous turn — or to turn 0;
- a message that **reappeared after a newer one had opened** had its late blocks attributed
  to the newer message's turn.

Both are now fixed by making the Ledger own turn numbering (`observe()` returns the turn a
record's blocks belong to) rather than letting each caller keep a counter, and both have
assertions that fail on the old behaviour. The second shape is measured at 3 of 197,127
message openings on this corpus, all in one transcript — rare, and real.

The same review is why the equivalence claim in §4 is stated with its scope: forcing
`identity` to `None` reproduces the pre-fix arithmetic **on transcripts where every assistant
record carries usage**, which is all 377,648 of them here, and is not a universal identity —
the old code counted a model name on records with no usage, and this one does not.

## 3. Consumers audited

Every file that reads token usage was classified. **No file in the repository reads usage
from an API response object** — there are no `--output-format json` or SDK-result readers —
so every usage number in this repository came from transcript records and every one of them
was exposed.

Repaired directly: `tools/carry.py`, `tools/extract.py`, `tools/b2t_validate.py`,
`tools/bashcost.py`, `tools/prefix.py`, `experiments/skill-ab/price.py`,
`experiments/skill-ab/rig_confirmatory.py`, `experiments/truth/rig_truth.py`,
`experiments/presentation/rig_pres.py`, `experiments/presentation/activation_probe.py`.

Repaired by inheritance (they call `carry.scan` / `carry.accumulate` / `vnext.metrics`):
`tools/optimize.py`, `experiments/vnext/rig.py`, `experiments/aivos/rig_aivos.py`,
`experiments/aivos/bash_residue.py`, `experiments/presentation/reconstruct.py`.

`tools/b2t_validate.py` needed more than a dedup. Its control — *drop turns containing a
tool_use or thinking block* — was written for whole-message records. Under the real format a
message that wrote prose **and** called a tool has a text-only record whose `output_tokens`
bills the tool JSON too, so that record passed the control while carrying exactly the
contamination the control existed to remove. Samples are now reassembled per message before
the control is applied.

## 4. Is the "old" column really what the repo printed?

Yes, and it was checked rather than assumed. The old column is produced by the repaired code
with `msgid.identity` forced to `None`. Compared field by field against
`tools/carry.py` as it stands at `ab501875` over 120 real transcripts: turns, the full items
list, the usage counter, model counts and runtime counts were **identical on 120 of 120
files, 0 mismatches**. The old numbers below are numbers this repository actually produced.

## 5. Impact, measured

Both passes ran over the same pinned list in one process (1,398 discovered, 1,394 pinned
after excluding files modified in the last 15 minutes, 1,360 parsed). `carry.accumulate`
rejects any file whose identity moves under the read, and the per-file content digests of
the two passes were compared afterwards: **DIGEST_DRIFT = 0**. The delta below is the
accounting fix and nothing else.

50+ turn cohort, this host, 21 Sep 2026:

| claim | old | new | abs | rel | affected |
|---|---|---|---|---|---|
| cohort sessions | 166 | 152 | −14 | **−8.43%** | YES |
| cohort turns | 115,422 | 59,205 | −56,217 | **−48.71%** | YES |
| input_tokens | 68,556,450 | 20,739,872 | −47,816,578 | −69.75% | YES |
| output_tokens | 150,120,545 | 65,969,295 | −84,151,250 | −56.06% | YES |
| cache_read | 45,182,880,291 | 24,141,034,610 | −21,041,845,681 | −46.57% | YES |
| cache_creation | 923,794,084 | 388,486,996 | −535,307,088 | −57.95% | YES |
| carry total | 161,315,792,936 | 90,542,043,126 | −70,773,749,810 | −43.87% | YES |
| cache_read share of volume | 97.534% | 98.070% | +0.536 pp | — | marginally |
| **Bash + Read share of carry** | 68.573% | 68.526% | **−0.047 pp** | — | **no** |
| Bash bytes/turn | 879.4 | 1,693.1 | +813.7 | +92.5% | YES |
| Read bytes/turn | 322.3 | 624.1 | +301.8 | +93.6% | YES |
| record-to-message ratio | — | — | — | **1.9495** | — |

Read this table as two different facts:

- **Absolute counts were roughly doubled.** Turns, every token total, and carry in bytes.
- **Shares barely moved.** The headline conclusion of §1 of FINDINGS — that Bash and Read
  results are where a session's context goes — is a share, and it survives to two decimal
  places. `cache_read`'s share of volume moves half a percentage point, because the
  duplication factor is per message and not perfectly uniform; it is not the exact invariant
  the "ratios self-correct" shorthand suggests, and it is not far off either.

Byte-level facts are untouched by construction, and that was checked too: over 300
transcripts the overwrite count is **152 old, 152 new** while the turn count in the same
sample halves (35,830 → 18,832). **The 741 overwrites and the 20.8% byte-identical share do
not move.** Content blocks are not deduplicated, so nothing counted per block changes.

Bytes-per-token, recomputed over the whole corpus with samples reassembled per message:

| | old, per record | new, per message |
|---|---|---|
| Indonesian | 1.8978 (n = 2,930) | **1.9583** (n = 2,877) |
| English | 2.1475 (n = 47) | **2.1300** (n = 38) |

The Indonesian constant moves +3.2%. The English figure rests on 38 usable samples on this
corpus and is reported here only to show that it moved by −0.8%; the published **3.32** for
English is not reproduced by this corpus at any accounting and should not be cited from a
sample this small.

## 6. What could not be recomputed, and what that costs

**The published headline population no longer exists.** `docs/FINDINGS.md` cites 1,316
transcripts / 237,541 assistant turns from August 2026, and a 421-session cohort of 233,549
turns. This host today discovers 1,398 transcripts and a 152-session cohort. Those figures
are therefore `CANNOT_RECOMPUTE` on their own population: the correction factor above
(≈1.95 records per message) is measured on a later corpus of the same host and same
workflow, and is offered as the scale of the error, not as a restatement of the number.
Per §15 the original numbers stay where they are, marked.

**The skill-A/B confirmatory run cannot be recomputed at all.** `rig_confirmatory.py` read
its transcripts from `experiments/skill-ab/cfg_plain` and `cfg_cav`, which no longer exist,
and its preserved ledger stores one row per *record* with no `message.id`, so the rows cannot
be re-identified after the fact. `−22.7%` output tokens for one terseness sentence, the
`−0.8%` skill-versus-sentence comparison and the `−1.7%` end-to-end figure are all
`CANNOT_RECOMPUTE`.

That matters more than a missing decimal, because the artefact is **not** constant between
arms. Where the raw transcripts *were* preserved — the presentation experiment, 320
transcripts under `experiments/presentation/cfg_pres`, all 64 ledger rows resolvable — the
inflation differs per arm:

| arm | turns old | turns new | ratio | output old | output new |
|---|---|---|---|---|---|
| A | 113 | 46 | 2.457 | 25,118 | 9,902 |
| B | 104 | 42 | 2.476 | 24,177 | 9,505 |
| C | 99 | 44 | 2.250 | 22,748 | 9,583 |
| D | 106 | 45 | 2.356 | 23,151 | 9,397 |
| Dh | 106 | 45 | 2.356 | 23,780 | 9,390 |
| Dm | 103 | 42 | 2.452 | 26,015 | 9,991 |
| E | 108 | 48 | 2.250 | 22,433 | 9,449 |
| F | 86 | 38 | 2.263 | 23,260 | 9,394 |

The ratio spans 2.250 to 2.476 — a **10% spread between arms of one experiment**, and up to
**3.7 percentage points** of apparent output-token difference that is accounting, not
behaviour. Across the wider corpus the per-session ratio has mean 2.035, median 1.984,
sd 0.348, **CV 17.1%**, range 1.263 to 3.897.

A crude per-arm aggregate of the table above reorders the arms: measured against arm A,
arm C reads −9.44% under the old accounting and −3.22% under the new, and arm E falls from
the largest reduction to the middle of the field. That aggregate is *not* the published
statistic — the published analysis is paired, filtered by verdict, and computed by
`analyze_pres.py` — so the right conclusion is not a new number but a status:

**CONCLUSION_CHANGED_REQUIRES_OWNER_REVIEW** for every arm comparison in `docs/VNEXT.md`.
The transcripts are preserved and `reconstruct.py` exists, so this is work that can be done;
it is deliberately not done here, because re-running an experiment's analyzer and restating
its result is an owner decision, not a bug fix.

## 7. What did not change

- `OVERALL_SAVINGS_STATUS` = **NOT_PROVEN**, unchanged. The −1.7% end-to-end figure was
  already smaller than the same rig's variance between two byte-identical arms; it now also
  carries an accounting artefact with a 17% between-session spread. A negative result does
  not become positive by being measured worse.
- `CORRECTNESS_STATUS` — untouched. Nothing here bears on the correctness claims, which are
  scored from diffs and verdicts, not from token counts.
- The canonical SameWrite skill body: `7edec9f21e0bd50583e388e0bdc177f92ba8f0db6ce2bb61acd52b39d81e7767`,
  byte-identical, as is its description. No promotion, no candidate persistence, no hook
  behaviour changed.
