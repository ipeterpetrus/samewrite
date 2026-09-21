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
  whether or not that record carries usage. A block on a record that arrives before the usage
  does therefore lands on its own message's turn rather than on the one before it.
- **item position** — by where the item entered the **file**, not by which message owns it.
  carry is a replay cost: an item is billed on every turn after the one it was sent on. For
  the 3-in-197,127 records belonging to a message that a newer one has already overtaken,
  indexing the item at its message's turn would move it earlier than it was ever sent and
  overstate its carry. Identity governs the turn COUNT and the BILL; file order governs
  position. A second review round moved this line, after the first fix put those blocks back
  on their message's turn and a reviewer asked what carry is actually measuring.
- **usage** — billed once per identity, from the first record that carries it. All observed
  copies are identical, so first and last are the same number today; `usage_conflicts` counts
  the day that stops being true instead of silently picking a winner.
- **blocks** — *not* deduplicated. Identity is a message-level law. The prose block and the
  tool_use block of one message remain two items, and both belong to that message's turn.

`tests/test_multiblock.py` (40 assertions) pins all four, including two mutation oracles: an
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

A second, confirmation round on the fixed code closed both ordering findings and found two
more, both now fixed: `carry.render` printed the identity notes only on its markdown branch,
so the default CLI output never showed them; and `tools/prefix.py` kept a
`'"usage"' not in line` prefilter, which skipped exactly the usage-less first record that now
opens a turn — so its turn count no longer matched `carry.py`, which is the one thing that
function exists to do.

Two findings were NOT code-fixed in the first pass, and were stated here rather than closed
quietly. **Both are now closed in §8** — H2 in code, H1 in code as far as the format permits,
with the remainder named as a source-format limitation. The paragraphs below are kept as the
record of what was open, and of what the fix owed:

- **Two genuinely different messages sharing one `message.id` merge into one.** No transcript
  can distinguish that from one message written twice. The law assumes vendor ids identify a
  message. `out_of_order` catches the non-adjacent form (and an anonymous record now breaks
  adjacency too, so `X → anonymous → X` is counted); a consecutive collision would not be
  caught at all.
- **A provisional-then-final usage pair would bill the provisional copy.** First-wins is what
  the measurement supports — 0 differing copies in 127,934 multi-record messages — and
  switching to last-wins on zero evidence would be a guess. What the fix owes is visibility,
  and that is now real: `usage_conflicts` is aggregated and printed in both output modes.

Both were residual HIGHs by the reviewer's rating, open on purpose with an observable each.
§8 closes them: differing usage is now refused rather than billed first-wins, and a collision
detectable from the transcript now fails closed instead of merging. What §8 does not do is
claim the undetectable case away.

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
| carry total | 161,315,792,936 | 90,542,042,853 | −70,773,750,083 | −43.87% | YES |
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

## 8. H1 / H2 closure — ambiguous input must not become an exact output

The two findings §2 left open as residual HIGHs are closed here, and the closure is
deliberately asymmetric: H2 was an implementation defect and is fixed in code; H1 is
partly an implementation defect (a detectable collision was not detected) and partly a
property of the source format (an undetectable one cannot be). Both halves are stated.

### 8.1 What the format can actually prove

Re-measured on this machine, structure only — record `type`, `message.id`, `message.usage`,
block types and the candidate metadata fields; no prompt, no tool input, no tool output, no
path, no content. Discovery is now de-duplicated by real path, and three config directories
symlink `projects/` to one archive, so the 1.4.1 figures in §1 counted that archive three
times. The ratios are unchanged; the absolute counts were not:

| | 1.4.1 (tripled) | 2026-09-21 (de-duplicated) |
|---|---|---|
| transcripts | 4,143 | **1,399** |
| assistant records | 377,648 | **126,258** |
| distinct `message.id` | 196,759 | **65,815** |
| multi-record identities | 127,934 | **42,793** |
| of those, usage identical | 127,934 | **42,793 (100%)**, 0 differing |
| records with no usable id | 3 | **1** |
| reappearance events | 3 | **1**, in 1 transcript |

For every record sharing one non-empty `message.id`, each candidate metadata field was
measured for agreement. `POPULATION` counts identities where at least one record states the
field; `MISSING` counts records that do not:

| field | population | same | different | missing | invariant |
|---|---|---|---|---|---|
| `message.role` | 42,793 | 42,793 | 0 | 0 | YES |
| `message.model` | 42,793 | 42,793 | 0 | 0 | YES |
| `message.type` | 42,793 | 42,793 | 0 | 0 | YES |
| `message.stop_reason` | 42,793 | 42,793 | 0 | 0 | YES |
| `message.stop_sequence` | 42,793 | 42,793 | 0 | 0 | YES |
| `requestId` | 41,525 | 41,525 | 0 | 4,208 | YES |
| `sessionId`, `cwd`, `version`, `gitBranch`, `entrypoint`, `isSidechain`, `userType`, `effort` | 42,229–42,793 | all | 0 | 0–1,296 | YES, but useless |
| `uuid` | 42,793 | 0 | **42,793** | 0 | NO |
| `parentUuid` | 42,793 | 0 | **42,793** | 0 | NO |
| `timestamp` | 42,793 | 0 | **42,793** | 0 | NO |
| `apiBlockIndex` | 20,637 | 0 | **20,637** | 53,675 | NO |

Six fields become guards: the five message-level ones and `requestId`. The session-level
constants are invariant and are *not* used — they never differ between two messages of one
transcript either, so they discriminate nothing; adding them would look like six more guards
and be worth zero. The four per-record fields are excluded for the opposite reason: guarding
on one would reject every legitimate multi-block message in the corpus.

### 8.2 The one reappearance, inspected

`out_of_order = 1`, one transcript, three records of one identity at file ordinals 121, 123
and 124 with an unrelated record at 122. Structure only:

```
ordinal 121  blocks [thinking]   usage (2, 675, 185525, 614)  requestId R  ts 2026-08-28T18:19:06Z
ordinal 122  blocks [text]       — a DIFFERENT identity       requestId S  ts 2026-08-30T08:20:48Z
ordinal 123  blocks [tool_use]   usage (2, 675, 185525, 614)  requestId R  ts 2026-08-28T18:19:08Z
ordinal 124  blocks [tool_use]   usage (2, 675, 185525, 614)  requestId R  ts 2026-08-28T18:19:09Z
```

All three records of the identity agree on every guard field, carry identical usage, hold
three *different* block types, and form an unbroken `uuid → parentUuid` chain
(121 → 123 → 124). The interrupting record is two days newer and belongs to another request.

    LEGITIMATE_REAPPEARANCE_PROVEN = YES
    DISTINCT_MESSAGES_PROVEN       = NO
    FORMAT_CANNOT_DISTINGUISH      = NO   (for this case)

"Proven" here means: proven under the documented upstream assumption in §8.5, plus a
contiguous parent chain that a two-message interpretation would have to break.

### 8.3 H2 — differing usage is refused, not resolved

`tools/msgid.py` no longer bills the first copy when the copies disagree. There is no
FIRST_WINS, LAST_WINS, MAX_WINS, MIN_WINS or SUM, because no upstream invariant authorises
one. A `Ledger` is **strict by default**: a differing copy raises `msgid.Ambiguous`, and the
only caller that opts out is `tools/carry.accumulate`, whose contract is to exclude the
source and say so rather than abort a sweep of a thousand files. Missing usage on one record
is *not* a conflict — the copy that exists is the bill, in either ordering.

Two more escapes of the same family were found by the review and closed. `price.py` and
`rig_confirmatory.py` still carried the `'"usage"' not in line` prefilter that §2 had already
removed from `prefix.py`, so a usage-less record — exactly where a collision hides — never
reached a guard; `b2t_validate.py` carried an `'"output_tokens"' not in line` one with the
same effect. Replacing them with an `'"assistant"' not in line` test was the *first* repair
and it was wrong: a confirmation round defeated it with `"type":"\u0061ssistant"`, which is
valid JSON that no substring test sees, and which also silently changed which records were
billed. **No substring prefilter survives that, so there is none left** — these readers parse
every line, as `carry.py` already did over the same corpus. Widening `b2t_validate`'s loop
also changed what a calibration SAMPLE is, deliberately: a usage-less record of a message now
contributes its text to that message's numerator and its block types to the tool_use/thinking
control, which is what the function's docstring always claimed ("whichever record carried it")
and what the prefilter quietly prevented. Measured over 300 transcripts, before and after:
n=844, median 2.00 B/tok, slope 1.94 — identical, because every record there carries usage.

And `b2t_validate` reads a FIFTH usage field, `output_tokens_details.thinking_tokens`,
which the four-counter conflict tuple does not cover: two records agreeing on the four and
disagreeing on that one made its thinking-token control depend on which record the file wrote
first. It now drops the calibration sample instead, in either order.

Fail-closed propagation is mechanical, not documentary. `scan_full` empties the usage counter
when the ledger is not exact, so no caller can receive an ambiguous total; the aggregate
excludes the source from every figure and reports it as
`usage_conflicted_transcripts` / `usage_exact_measurement_excluded`; and
`tests/test_multiblock.py` drives **every** consumer that reads `message.usage` with the same
conflicting fixture and asserts each one refuses. The two rigs that glob their own run
directories and cannot be driven from a test are covered by the property that makes the rest
true, asserted repo-wide: no module outside `carry.accumulate` constructs a non-strict Ledger.
A conflict is also never filed as `unreadable` — that counter means bytes could not be read,
and burying a conflict there would be the silent discard this section exists to prevent. Nor
is a conflicted source listed in the evidence manifest: `parsed` is the set of sources the
payload's numbers came FROM, and an entry for a source that contributed nothing is what lets
a reader call a sweep INTACT when it measured around a conflict. The frozen contract has no
outcome named "read, and then refused", so the source is left to `not_attempted` — a loss
counter — with the detail in `records_rejected`. That is checked against the READER's own
function, not asserted: `evidence.certificate` derives **DEGRADED** for a sweep that refused
one source of two, **INTACT** for a clean one, and a sweep whose only source was conflicted
emits `CarrySweepFailed` rather than a measurement of zero. Claiming an outcome the reader
cannot name was the first repair, and it turned a correctly-refused source into a certificate
ACCOUNTING VIOLATION — the producer accusing itself of being broken instead of reporting a
loss. The confirmation round caught that.

One more path was checked and closed, and it took three attempts to get right. A record larger
than `MAX_LINE` used to be skipped *before* it was parsed, so an oversize assistant record
reached neither guard and "no conflict found" was really "not looked at". `MAX_LINE` exists so
one enormous line cannot dominate the item table, not to avoid reading it — and the bytes are
already in memory, since the line had to be read to be measured. It is therefore parsed,
guarded and **billed** like any other record now, and only its content blocks are kept out of
the item table, which is the whole of what the limit was ever for; `oversize` still counts it
and the sweep still reads PARTIAL. The first repair decided this from a substring test on the
unparsed bytes and `"type":"\u0061ssistant"` defeated it; the second parsed the record but
dropped its bill along with its blocks, publishing a token total that was too LOW. Both were
caught by confirmation rounds, which is what confirmation rounds are for.

A line the parser cannot read at all stays what it always was: a counted line-level loss, not
a conflict. The distinction is deliberate. A conflict is two incompatible statements; a
malformed line is an **absent** one, and the frozen certificate already carries `malformed` as
a loss counter, so a sweep holding one cannot read INTACT and its reader is already told the
transcript was not fully read. Refusing the source instead would replace a precise report with
a blunt one, and would exclude every live session whose last line is half written. Measured:
0 malformed and 0 oversize lines in 1,390 transcripts.

Removing the prefilters also corrected *which* records carry a bill, and this is a behaviour
change worth stating rather than burying. The old `'"usage"' not in line` filter in `price.py`
and `rig_confirmatory.py` passed any record whose line contained a usage object — including a
**user** record that carried one — so those rigs could count a turn `carry.py` does not. They
now bill assistant records only, which is the definition `carry.py` has always used, and
`tests/test_multiblock.py` pins it. On a transcript where every record is an assistant record
the two behaviours are identical.

### 8.4 H1 — detectable collisions fail closed

A repeated identity whose records state **different** values for a proven-invariant field is
a `MESSAGE_IDENTITY_CONFLICT`. It is not merged and it is not split: the source leaves every
aggregate, and `identity_conflicted_transcripts` / `identity_exact_measurement_excluded` say
so. A field that is absent, or explicitly null, states nothing and is never read as a
disagreement — otherwise the guard would start rejecting legitimate serialisations the day
the CLI writes `stop_reason` only on a message's last record. A reappearing identity is
still not a collision; `out_of_order` counts it, and a mutant that calls every reappearance a
collision turns the suite RED against the fixture modelled on §8.2.

### 8.5 The residual, stated rather than assumed

    CAN_TWO_DISTINCT_LOGICAL_MESSAGES_REMAIN_STRUCTURALLY_INDISTINGUISHABLE
    FROM_ONE_MULTIBLOCK_MESSAGE = YES

The indistinguishable class is **not** "two messages that agree on all six guards". It is
wider than that, and stating it narrowly would understate the limitation. The guard compares
only values that are *stated*: a field that is absent, or explicitly null, states nothing.
So the residual is:

> two assistant messages sharing one `message.id` on which **nothing states two different
> values** — no guard field, and no billed usage counter. That includes every case where one
> message states something and the other omits it: a `requestId` present on one and absent on
> the other (it is absent on 4,208 records here, so this is a real shape, not a hypothetical),
> and equally a message that carries usage beside one that carries none, since missing usage
> is deliberately not a conflict. Two messages whose four billed counters merely *differ* are
> caught by H2; two where only one of them states them at all are not.

Nothing in a transcript separates that from one message written as several content-block
records. That is not a defect in this code: the information is not in the file. Treating an
absent field as a disagreement would not recover it either — it would reject the legitimate
multi-block messages the corpus is actually made of, which is the opposite error and the
worse one.

    SOURCE_FORMAT_LIMITATION = YES
    UPSTREAM_ASSUMPTION      = within one transcript, a non-empty `message.id` identifies
                               exactly one logical assistant message — including when
                               `requestId` or any other guard field is absent from some or
                               all of its records

That assumption is *used*, not proven. What changed is that it is now bounded on both sides:
every violation the format can expose is detected and fails closed, and the part that remains
is named and written down here instead of living in a docstring as a caveat.

Two things must not be confused, and an earlier draft of this section did confuse them. What
is **measured at 0** on this corpus is the DETECTABLE conflicts: 0 usage conflicts and 0
identity collisions across 42,793 multi-record identities. The indistinguishable class above
is, by construction, **not observable** — if it could be counted it would not be
indistinguishable — so no occurrence count can be claimed for it, in either direction. The
honest statement is that it has an unknown size and no known instance.

### 8.6 Numerical effect

Compared against the repaired HEAD, not against broken `main`. The corpus is a **pinned file
list of 1,390 transcripts**: the 9 files a live session was still appending to were excluded
from **both** runs, each file's size and mtime were recorded when the list was pinned, and
re-checked before each run and again after the last one — 0 drifted. Without that pinning the
comparison is worthless: a first attempt showed "turns 63,461 → 63,475" that was entirely the
observing session writing its own transcript between the two runs.

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

Measured by the shipped ledger over that same pinned list: 115,558 assistant records, 59,869
distinct ids, 39,289 multi-record identities, **0 usage conflicts, 0 identity collisions**, 1
reappearance, 0 malformed lines and 0 oversize lines. (The wider table in §8.1 was measured
over all 1,399 discovered transcripts, live files included, which is why its counts are
larger; the before/after comparison uses the pinned subset because only that one cannot move
between runs.)

Unchanged, and for a stated reason rather than by construction: nothing was excluded, because
there was nothing to exclude. A corpus that did contain a conflict would report a different,
smaller population — which is the point.

`TOTAL_SAVINGS` remains **NOT_PROVEN**. No p-value, arm ranking, savings percentage or
promotion conclusion is recomputed here; that needs owner authorisation after the accounting
semantics are frozen.
