# v1.4.2 — frozen counterexample matrix

Written **before** the repair, against `main` at `77e3677`. Every expectation below is what the
optimizer *must* do; the second block records what it actually did when the matrix was frozen. An
expectation may only change afterwards if the original expectation is independently proven wrong,
and the change must be recorded in §3.

Scope: the **legacy** optimizer path (`tools/optimize.py`, history schemas 0/1/2, live sweeps from
`tools/carry.py`). Schema-4 typed evidence stays unsupported by this optimizer and the v1.4 typed
promotion stays shadow-only; neither is touched here.

## 1. The matrix

| case | fixture | status | strict exit | candidate files | comparable | evidence quality |
|---|---|---|---|---|---|---|
| **R142_01** | 6 schema-2 records, `evidence_quality=PARTIAL`, `skipped_by_limit=5`, no live sweep, no flag | `PARTIAL_EVIDENCE` | 40 | 0 | 6 | `PARTIAL` |
| **R142_01P** | same fixture **with** `--accept-partial` | `CANDIDATE` | 10 | 1 | 6 | `PARTIAL` |
| **R142_02** | 6 eligible `COMPLETE` records + 1 newer `INVALID` record (`sessions=0`, `scanned>0`), incomparable corpus size | `CANDIDATE` | 10 | 1 | 6 | `COMPLETE` |
| **R142_03** | 6 `COMPLETE` records whose runtime set changes mid-history, share moving ≥ 5 pp | `HOST_BEHAVIOR_SHIFT` | 30 | 0 | 6 | `COMPLETE` |
| **R142_04** | 6 records claiming `COMPLETE` with `sessions=turns=carry_bytes=0` | `PARTIAL_EVIDENCE` | 40 | 0 | 0 | `INVALID` |
| **R142_05** | live sweep over a transcript holding one torn JSON record, with **and** without `--accept-partial` | `PARTIAL_EVIDENCE` | 40 | 0 | 0 | `DEGRADED` (`carry` reports `PARTIAL`, never `COMPLETE`) |
| **R142_06** | `--max-files 1` where discovery order is the reverse of mtime order | carry sweep and skill-listing scan select the **same single source** (the newest) | — | — | — | — |
| **U1** | 6 schema-1 records (a generation with no `evidence_quality` field), with and without `--accept-partial` | `PARTIAL_EVIDENCE` | 40 | 0 | 6 | `UNKNOWN` |
| **P1** | 6 `COMPLETE` records, acquisition counters all zero | `CANDIDATE` | 10 | 1 | 6 | `COMPLETE` |
| **P3** | P1's population + one `INVALID` record in **another scope** | `CANDIDATE` | 10 | 1 | 6 | `COMPLETE` |
| **P4** | one current-generation (schema-4 envelope) record | `INSUFFICIENT_DATA` | 20 | 0 | 0 | unsupported, refused by name |
| **S_NOACTION** | 6 `COMPLETE` records, share flat (no finding over threshold) | `NO_ACTION` | 0 | 0 | 6 | `COMPLETE` |
| **S_LOCK** | P1's fixture with the emit lock already held | `ALREADY_RUNNING` | 41 | 0 | 6 | `COMPLETE` |

Quality vocabulary for the legacy law (worst wins, never a majority):

```text
COMPLETE < PARTIAL < DEGRADED < EMPTY < UNKNOWN < INVALID
```

* `PARTIAL` = a bound the caller chose (`--max-files`). Only this one is rescued by
  `--accept-partial`.
* `DEGRADED` = evidence that was selected and then lost (unreadable, oversize, malformed,
  identity changed under the read, conflicting records). A loss is never a chosen bound, so
  `--accept-partial` does not accept it.
* `UNKNOWN` = the record cannot attest its own quality: a schema older than the field, or a
  schema-2 record without the acquisition counters its writer always wrote.
* `INVALID` / `EMPTY` = the producer's own terms for a sweep that found nothing usable, plus any
  record whose own numbers contradict its claim.

## 2. Observed on `main` 77e3677 when the matrix was frozen

Run against these exact fixtures, before a line of the repair existed:

```text
R142_01    CANDIDATE            exit 10  files 1  comparable 6   bounded history promotes
R142_01P   CANDIDATE            exit 10  files 1  comparable 6   the flag changed nothing: it was never read
R142_02    INSUFFICIENT_DATA    exit 20  files 0  comparable 0   the INVALID record anchored, six eligible stranded
R142_03    HOST_BEHAVIOR_SHIFT  exit 30  files 1  comparable 6   the refusing status still wrote the file
R142_04    CANDIDATE            exit 10  files 1  comparable 6   sessions=turns=carry_bytes=0 promoted
R142_05    carry quality=COMPLETE, malformed=1                   a lost record is not a loss
R142_05    NO_ACTION            exit 0   files 0                 and the run reports nothing wrong
R142_06    listing sample read the OLDEST transcript             two definitions of one bound
U1         CANDIDATE            exit 10  files 1  comparable 6   a field that never existed read as COMPLETE
P1         CANDIDATE            exit 10  files 1  comparable 6   (already correct)
P3         INSUFFICIENT_DATA    exit 20  files 0  comparable 0   an invalid record in ANOTHER scope chose the scope
P4         INSUFFICIENT_DATA    exit 20  files 0  comparable 0   (already correct)
S_NOACTION NO_ACTION            exit 0   files 0  comparable 6   (already correct)
S_LOCK     ALREADY_RUNNING      exit 41  files 0  comparable 6   (already correct)
```

## 3. Deviations from the frozen expectations

None.

## 4. Cases added AFTER the freeze

Not changed expectations — new rows, each from an attack on the repair itself rather than on the
original defect. They are listed separately so the frozen matrix stays readable as what it was.

| case | fixture | expectation |
|---|---|---|
| **R142_07** | two records sharing one `run_id`, the first `COMPLETE`, the retry `PARTIAL` with `skipped_by_limit=7` | the retry is dropped as an observation and counted, and the quality it reported travels with the record that survives: `PARTIAL_EVIDENCE` / exit 40 / 0 files, `CANDIDATE` with `--accept-partial` |
| **R142_07b** | `schema_version` of `"2"` (string) or `2.0` (float) | `UNKNOWN` — a version this reader cannot name is not a newer generation to trust |
| **R142_08** | schema-2 record with zeroed counters and no `sessions` / `turns` / `carry_bytes` at all | `UNKNOWN` — zero counters say nothing went wrong, not that a sweep happened (cross-family review, round 1) |
| **R142_09** | `--max-files 2` where one of three sources cannot be dated | the datable sources still order by mtime; one unreadable mtime no longer sends the whole selection back to a discovery-order slice (cross-family review, round 1) |

Confirmation round, attacking the repair again:

| case | fixture | expectation |
|---|---|---|
| **R142_15** | a `PARTIAL` claim with every counter at zero | `UNKNOWN` — a bound shows up in `skipped_by_limit` and a loss in a loss counter; a claim no counter can explain is not a bound `--accept-partial` may adopt |
| **R142_15b** | a record carrying `malformed`, `malformed_lines`, `identity_changed`, `conflicted_sources` or `records_rejected` | `DEGRADED` — a loss must be honoured wherever the reader can see it, not only in the two counters the first cut looked at |
| **R142_16** | history + one record from an unsupported schema 3, and one whose shares sum to 10 | `PARTIAL_EVIDENCE` / exit 40 / 0 files — a rejected line is damage unless it is a refusal by design, a deduplicated retry, or a line that was never a carry record (control: a foreign line still promotes) |
| **R142_17** | ledger of 100 `checked` lines plus one `{"event": "garbage"}` | the unaccountable line counts as rejected and the guard only observes |

## 5. B1 — the blocker an independent acceptance review found, and the epoch matrix

The first head of this branch closed the six original defects (§1–§4) and introduced one of its own.
An **independent acceptance review of PR #13 BLOCKED it**: container damage was permanent. One torn
line — the crash fragment `docs/MULTI_AGENT.md` §Concurrency calls an expected event, the one the
reader is designed to "reject exactly that line and count it" — set the whole file to `DEGRADED`
forever. Nothing in the product expires, rotates or repairs a history (`docs/MULTI_AGENT.md`: "The
optimizer does not schedule, expire or rotate"), and `--accept-partial` cannot adopt `DEGRADED` by
design, so a single crash permanently disabled promotion for **every scope** sharing
`~/logs/carry_history.jsonl`.

Measured on that head before the repair (every row: zero candidate files, exit 40, forever):

```text
6 good + torn                         PARTIAL_EVIDENCE  exit 40  comparable 6   hq DEGRADED
6 good + torn + 2 good                PARTIAL_EVIDENCE  exit 40  comparable 8   hq DEGRADED
6 good + torn + 6 good                PARTIAL_EVIDENCE  exit 40  comparable 12  hq DEGRADED
6 good + torn + 60 good               PARTIAL_EVIDENCE  exit 40  comparable 66  hq DEGRADED
scope-a good + torn + scope-b good    PARTIAL_EVIDENCE  exit 40  comparable 6   hq DEGRADED
torn first + 6 good                   PARTIAL_EVIDENCE  exit 40  comparable 6   hq DEGRADED
zero-carry record (shares {})         PARTIAL_EVIDENCE  exit 40  comparable 6   hq DEGRADED
6 good + torn + 60 good, --accept-partial               exit 40  (no flag can adopt a loss)
```

### The replacement: a history EPOCH, cut at the physical position of the loss

An unattributable loss cuts the promotion history **at that line's position in the file**. Evidence
before the cut and evidence after it are never combined for a promotion; the loss stays reported;
the newest epoch is, by construction, free of damage. No time window, no expiry, no ratio, no new
override flag — and `--accept-partial` still adopts only a caller's chosen bound, never a loss.

| case | fixture (physical order) | status | exit | files | comparable | active epoch | history.quality | boundaries |
|---|---|---|---|---|---|---|---|---|
| **B1_01** | 6 good, torn | `INSUFFICIENT_DATA` | 20 | 0 | 0 | 0 | `EMPTY` | 1 |
| **B1_02** | 6 good, torn, 2 good | `INSUFFICIENT_DATA` | 20 | 0 | 2 | 2 | `COMPLETE` | 1 |
| **B1_03** | 6 good, torn, 6 good | `CANDIDATE` | 10 | 1 | 6 | 6 | `COMPLETE` | 1 |
| **B1_04** | 6 good, torn, 60 good | `CANDIDATE` | 10 | 1 | 60 | 60 | `COMPLETE` | 1 |
| **B1_05** | scope-a 6 good, torn, scope-b 6 good | `CANDIDATE` (scope b) · `INSUFFICIENT_DATA` with `--scope-id a` | 10 · 20 | 1 · 0 | 6 · 0 | 6 · 0 | `COMPLETE` · `EMPTY` | 1 |
| **B1_06** | 6 good, torn, 6 good, torn, 6 good | `CANDIDATE` | 10 | 1 | 6 | 6 | `COMPLETE` | 2 |
| **B1_07** | torn, 6 good | `CANDIDATE` | 10 | 1 | 6 | 6 | `COMPLETE` | 1 |
| **B1_08** | 6 good, truncated final line | `INSUFFICIENT_DATA` | 20 | 0 | 0 | 0 | `EMPTY` | 1 |
| **B1_09** | 6 good, foreign JSON line | `CANDIDATE` | 10 | 1 | 6 | 6 | `COMPLETE` | 0 |
| **B1_10** | 6 good, schema-4 envelope line | `CANDIDATE` | 10 | 1 | 6 | 6 | `COMPLETE` | 0 |
| **B1_11** | 6 good, zero-carry record (`shares {}`, `carry_bytes 0`) | `CANDIDATE` | 10 | 1 | 6 | 7 | `COMPLETE` | 0 |
| **B1_12** | 6 records the law calls INVALID | `PARTIAL_EVIDENCE` | 40 | 0 | 0 | 6 | `EMPTY` | 0 |
| **B1_13** | 5 good, `run_id=X` good, torn, `run_id=X` good ×6 | `CANDIDATE` | 10 | 1 | 6 | 6 | `COMPLETE` | 1 |

Rules the matrix encodes:

* **Unattributable loss → file-global boundary.** An unparseable line, an oversized line or an
  unreadable file cannot name a scope, so the cut applies to every scope.
* **Parseable rejection carrying a readable `scope_id` → scope-local boundary.** Only that scope's
  continuity is cut; a sibling agent is not punished for a neighbour's corrupted record. Attribution
  trusts the record's own `scope_id` (a string of 1–64 characters, no control bytes) and falls back
  to file-global whenever it cannot be read.
* **Not damage, so not a boundary:** a well-formed foreign JSON line, current-generation (schema-4)
  evidence refused by design, and a deduplicated retry.
* **The damage is still reported** — `history.rejected` counts it and `history.damage` says how many
  boundaries the file holds — while `history.quality` describes only the evidence eligible for the
  CURRENT analysis. A historical gap stays true while the post-gap evidence is independently
  complete.
* **`history.quality` with nothing comparable is `EMPTY`, never `COMPLETE`** (the acceptance
  review's MEDIUM M1).
* **A zero-carry sweep is readable evidence, not corruption** (MEDIUM M2). `carry.py` says it in its
  own report — "A session whose every item lands on its final turn carries nothing" — the 1.3 writer
  emits `shares: {}` for it and the current writer guards `if C else {}`. Measured on this branch:
  `carry.accumulate()` on such a transcript returns `sessions=1 turns=6 carry_total=0`. The record
  is `EMPTY` for the quality law: nothing to compare, and nothing wrong with the file.

### 5.1 Deviations from this frozen matrix

None.
