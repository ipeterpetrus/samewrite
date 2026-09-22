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

### 5.2 Expectations the epoch model supersedes

Three rows written for the first head's permanent-damage model are now wrong, and are replaced
rather than quietly re-run. In each, the damaged line sits at the END of the file, so there is no
post-loss epoch: the outcome is still **no promotion and no candidate file**, and what changes is
only the word for it and whether later evidence can ever clear it.

```text
R142_11  torn line in the history        PARTIAL_EVIDENCE / DEGRADED  ->  INSUFFICIENT_DATA / EMPTY
R142_15  unsupported schema, bad shares  PARTIAL_EVIDENCE / DEGRADED  ->  INSUFFICIENT_DATA / EMPTY
R142_18  carry record with no shares KEY PARTIAL_EVIDENCE / DEGRADED  ->  INSUFFICIENT_DATA / EMPTY
```

Each keeps its protection and gains a companion case: the same rejected line placed BEFORE a healthy
population, where the population after the loss must stand on its own. The records before the loss
are never counted with the records after it — `R142_11` pins that as `comparable == 2` for
`6 good + torn + 2 good`.

Dedup across a boundary is also new, and is stated rather than inherited: deduplication is
**per epoch**. The same `run_id` on the far side of a loss is that population's own observation and
is kept; inside one epoch the retry is still dropped, still counted, and still cannot launder the
survivor's quality (`tests/test_optimize.py` pins both).

### 5.3 What a cross-family lane found in the epoch repair itself

Two more places where the repair still consulted the population it had just cut, both reproduced
before they were believed and both now pinned by a case and a mutant:

| case | fixture | expectation |
|---|---|---|
| **B1_14** | six `stale` records, a torn line, and a ledger of 100 writes | the ledger finding may still promote — its evidence is the ledger — but the scope, and therefore the candidate id, comes from the current epoch or from nothing: `default`, never `stale` |
| **B1_15** | scope-local loss in `a`, six clean `a` records, scope-local loss in `b`, one `b` record sharing a `run_id` with `a` | the epoch stamp is a pair of counts, so two scopes can hold the same numbers; deduplication identity carries the scope, and `a` stays `COMPLETE` instead of inheriting `b`'s `PARTIAL` through the retry floor |

The long-run simulator was discarding the epoch it was handed, so it could combine records across a
loss; it now analyses `active_records()` like the CLI.

## 6. Trusted damage boundaries (frozen before the second repair)

Frozen against the branch head `e6c1f4f`, **before** any of it was implemented. The adversarial
review of the epoch model found that attribution was taken from the very line that had just failed
validation: a `scope_id` holding invalid UTF-8 survived `errors="replace"` as `U+FFFD`, read as a
"readable" label, and cut a scope that does not exist — while the real population kept crossing the
loss. §2 of that review reproduced it as `CANDIDATE`, one candidate file, twelve comparable records
spanning both sides of the gap.

The rule this section freezes is about provenance, not about Unicode:

> **A record that failed validation is not a trustworthy authority for its own scope attribution.**

Two consequences, and one deliberate trade:

* **Every rejection that is a loss is a FILE-GLOBAL boundary.** No rejected line may name a scope,
  whatever its `scope_id` looks like — `rev`, `agent-b`, a path, a 64-character label, or bytes that
  never decoded. This over-blocks: one corrupt line cuts scopes that were never damaged. That is the
  chosen half of the trade (§23 of the task), because epochs recover and a fail-open crossing of a
  real loss does not.
* **The history is read as BYTES and decoded strictly, per physical line.** `errors="replace"`
  destroyed the evidence that decoding had failed; a line that cannot decode is now a named
  rejection (`line is not valid UTF-8`) and a file-global boundary, and the reader continues at the
  next line rather than abandoning the file.
* **A scope-local boundary now has exactly one trusted source** (§6.2): a record that PASSED
  validation and whose own canonical loss counters prove that evidence was lost.

### 6.1 TUTF — invalid UTF-8 (all FILE_GLOBAL, no ghost scope)

Fixture unless stated: `6 clean scope=rev` + the bad line + `6 clean scope=rev`. The bad line is
SameWrite-shaped, holds invalid UTF-8 in the named field, and independently fails `valid_record()`
(its shares sum to 20, not ~100).

| case | bad line | boundary | `damage.scope_local` | active epoch | status |
|---|---|---|---|---|---|
| **TUTF_01** | invalid UTF-8 inside `scope_id` | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TUTF_02** | invalid UTF-8 inside `shares` | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TUTF_03** | invalid UTF-8 inside `run_id` | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TUTF_04** | invalid UTF-8 inside `workload_class` | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TUTF_05** | one undecodable line before every record (`bad + 6 clean`) | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TUTF_06** | one undecodable line at EOF (`6 clean + bad`) | FILE_GLOBAL ×1 | `{}` | 0 | `INSUFFICIENT_DATA` |
| **TUTF_07** | two undecodable lines (`6 + bad + 6 + bad + 6`) | FILE_GLOBAL ×2 | `{}` | 6 | `CANDIDATE` |
| **TUTF_08** | one undecodable line between two scopes (`6×a + bad + 6×b`) | FILE_GLOBAL ×1 | `{}` | 6 (`b`); 0 with `--scope-id a` | `CANDIDATE`; `INSUFFICIENT_DATA` |

In every row: no candidate may name a `run_id` from before the boundary, `scope.known` may not
contain a label that came from the rejected line, and no raw undecodable byte may appear anywhere in
the JSON output, the human output or a candidate file.

### 6.2 TSCOPE — a rejected record does not authenticate its own `scope_id`

Fixture: `6 clean scope=rev` + one rejected record carrying a syntactically perfect
`scope_id="ghost"` + `6 clean scope=rev`. Every row below is a loss.

| case | rejected record | boundary | `damage.scope_local` | active epoch | status |
|---|---|---|---|---|---|
| **TSCOPE_01** | shares sum to 20, not ~100 | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TSCOPE_02** | a non-numeric share value | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TSCOPE_03** | `sessions` negative (implausible) | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TSCOPE_04** | `evidence_quality` outside the vocabulary | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TSCOPE_05** | `schema_version: 3`, a legacy schema this reader cannot name | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TSCOPE_06** | a carry record with no `shares` key at all | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |
| **TSCOPE_07** | `record_type` is not `carry_run` | FILE_GLOBAL ×1 | `{}` | 6 | `CANDIDATE` |

Still **not** a loss, so still no boundary at all: a well-formed foreign JSON line, a bare object
with no `shares` and no sign of being ours, and current-generation (schema-4) evidence refused by
design. A migration must not read as file damage.

Canaries, each used as the rejected record's `scope_id`, each of which must leave
`damage.scope_local == {}` and must not appear in `scope.known`: `/etc/passwd.d/synthetic`,
`agent-b`, `rev`, a 63-character label, a 64-character label, a label holding control bytes, and a
label that never decoded. **Cardinality:** 2000 rejected lines carrying 2000 distinct `scope_id`
values produce `file_global == 2000`, `scope_local == {}` — attacker-controlled strings cannot add a
single public map key.

### 6.3 The hypothesis this repair had to test first: a VALID record that is DEGRADED

Reproduced on `e6c1f4f` before anything was designed for it, with a matched control:

```text
6 clean + 1 valid schema-2 record with unreadable=3 + N clean, scope agent-a
  N=2    PARTIAL_EVIDENCE / history.quality DEGRADED / 0 candidate files
  N=6    PARTIAL_EVIDENCE / history.quality DEGRADED / 0 candidate files
  N=60   PARTIAL_EVIDENCE / history.quality DEGRADED / 0 candidate files
control (identical populations, no degraded record)
  N=2,6,60                CANDIDATE / history.quality COMPLETE / 1 candidate file
```

`VALID_DEGRADED_FAIL_STUCK=YES`. The record passes `valid_record()`, so no rejection and no
boundary was ever considered; it stays in `comparable()` forever, and `history_quality()` is the
worst of that set. No amount of later healthy evidence clears it — the same fail-stuck shape the
epoch model was built to remove, reached through the one door the epoch model did not watch.

So §9 of the task applies, and narrowly. A **fully validated** record whose OWN canonical loss
counters prove degraded evidence creates a **scope-local** recovery boundary after itself. This is
trusted where a rejected line is not: the record passed structural validation, its `scope_id` is the
same field every accepted record publishes through `scope.known`, and the damage fact comes from
`RECORD_LOSS_COUNTERS`, not from guessing what a corrupt line meant.

| case | fixture (scope `a` unless stated) | boundary | active epoch | status | `history.quality` |
|---|---|---|---|---|---|
| **VD_01** | 6 clean + DEGRADED + 2 clean | SCOPE_LOCAL `{a: 1}` | 2 | `INSUFFICIENT_DATA` | `COMPLETE` |
| **VD_02** | 6 clean + DEGRADED + 6 clean | SCOPE_LOCAL `{a: 1}` | 6 | `CANDIDATE` | `COMPLETE` |
| **VD_03** | 6 clean + DEGRADED + 60 clean | SCOPE_LOCAL `{a: 1}` | 60 | `CANDIDATE` | `COMPLETE` |
| **VD_04** | VD_02, reading the candidate | — | — | the candidate names none of the pre-boundary `run_id`s, and not the degraded record's own | |
| **VD_05** | 6 clean + DEGRADED at EOF | SCOPE_LOCAL `{a: 1}` | 0 | `INSUFFICIENT_DATA` | `EMPTY` |
| **VD_06** | `6×a`, `6×b`, DEGRADED `a`, `6×a`, `6×b` | SCOPE_LOCAL `{a: 1}` | `a`: 6 · `b`: 12 | `CANDIDATE` both | `COMPLETE` |
| **VD_07** | 6 clean + valid `PARTIAL` by `skipped_by_limit=3` + 6 clean | **none** | 13 | `PARTIAL_EVIDENCE`; `CANDIDATE` with `--accept-partial` | `PARTIAL` |
| **VD_08** | 6 clean + a schema-1 record (`UNKNOWN`, cannot attest) + 6 clean | **none** | 13 | `PARTIAL_EVIDENCE` | `UNKNOWN` |
| **VD_09** | 6 clean + a valid `INVALID` record + a valid `EMPTY` (zero-carry) record + 6 clean | **none** | 14 | `CANDIDATE` | `COMPLETE` |

The degraded record belongs to the OLD epoch (§14): it sits before its own boundary, in physical
order, never in the population that recovers. Its degradation stays reported in `history.damage`.

`PARTIAL`, `UNKNOWN`, `INVALID` and `EMPTY` are deliberately excluded. Only an actual loss counter
cuts: a bound the caller asked for is an intentional population, a legacy schema that cannot attest
completeness is not proof that a line was lost, and an ineligible record is not a damaged one.

### 6.4 Retry and a trusted boundary (§15)

Deduplication identity becomes `(scope, FILE-GLOBAL epoch, run_id)` — the scope-local component is
deliberately **not** part of it. Across a file-global loss the reader cannot tell whether a repeated
`run_id` is the same run, so both copies stand (B1_13). Across a *trusted* scope-local boundary the
file is intact and the reader knows exactly what happened, so a repeated `run_id` is the same
logical run retrying, and the later copy is bookkeeping.

| case | physical order (scope `a`) | expectation |
|---|---|---|
| **VD_10** | `clean X`, `degraded retry X`, 6 clean | boundary `{a: 1}` after the degraded copy; both copies pre-boundary; `duplicate run_id (retry)` = 1; active epoch 6, `CANDIDATE`, `COMPLETE` |
| **VD_11** | `degraded X`, `clean retry X`, 6 clean | boundary `{a: 1}` after the degraded copy; the clean retry is dropped as the same run's bookkeeping and never becomes evidence in the recovered epoch; `duplicate run_id (retry)` = 1; active epoch 6, `CANDIDATE`, `COMPLETE` |

Neither order launders the loss into the recovered epoch, and neither poisons it forever.

### 6.5 File-global recovery is unchanged (§20, §21)

| case | fixture | expectation |
|---|---|---|
| **MSG_01** | `6×a`, `6×b`, torn line, `6×a`, `2×b` | `a`: epoch 6, `CANDIDATE`; `b`: epoch 2, `INSUFFICIENT_DATA`; nothing from before the cut helps either |
| **MSG_02** | the same with the sufficiencies reversed (`2×a`, `6×b` after the cut) | `a`: `INSUFFICIENT_DATA`; `b`: `CANDIDATE` |

File-global means every scope is cut **at that position**, never that a scope is disabled forever:
`B1_01`–`B1_04` still pin `+0 / +2 / +6 / +60`.

### 6.6 Frozen-decision amendments to §5 (§27)

Two rows of the B1 matrix were written against the old attribution rule and are wrong under this
one. Both are replaced rather than deleted, and the property each was protecting keeps a case.

```text
B1_13e  three copies of one run_id in one epoch, the middle one carrying unreadable=1
        was: history.quality DEGRADED, 2 duplicates, 0 files
        now: the middle copy is a VALID record proving a loss, so it cuts scope-locally.
             The property "the worst copy survives inside one epoch" moves to a fixture whose
             copies are PARTIAL/COMPLETE (no loss counter); the degraded-copy behaviour is
             VD_10/VD_11 above.

B1_15   two scope-local boundaries taken from two REJECTED lines
        was: damage.scope_local == {a: 1, b: 1} from rejected records
        now: rejected lines are file-global, so the same fixture yields file_global == 2.
             The property it protected — two scopes can hold the same epoch NUMBERS, so the
             deduplication identity must carry the scope — is re-pinned with the same shape
             built from TRUSTED sources: a valid DEGRADED record in each scope.
```

No other B1 or R142 expectation changes. `R142_01`–`R142_06` and `B1_01`–`B1_14` are re-run
unchanged.

### 6.7 The residual limit this repair does not close (§24)

`LEGACY_STRUCTURALLY_VALID_CORRUPTION_LIMITATION=YES`. A legacy flat record carries no integrity
tag. A corruption that turns one valid record into a *different* valid record — `scope_id` flipped
from `agent-a` to `agent-b`, a share vector rewritten to another vector that still sums to ~100 — is
indistinguishable from a record the producer meant to write. Nothing in this repair detects it, and
nothing can: the information needed to tell them apart is absent from the format. What the repair
does guarantee is narrower and checkable: a line that *fails* validation never supplies attribution,
and a line that cannot be decoded is never mistaken for one that can.

### 6.8 Deviations from this frozen section

None.
