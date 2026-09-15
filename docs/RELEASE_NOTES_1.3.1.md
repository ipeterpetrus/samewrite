# SameWrite 1.3.1 — release notes

**One fix.** The offline optimizer now fails closed when the evidence supporting a candidate
includes partial history that nobody accepted.

## What was wrong

`tools/optimize.py` read evidence quality from the **live sweep only**. The quality each history
record carries — written by the observer that produced it — never entered the decision. So a
history built from bounded sweeps (`carry.py --max-files N`, the normal way to keep a large profile
affordable) produced a candidate exactly as if the corpus had been swept in full, and a complete
live scan masked it.

Measured on the released 1.3.0 code:

```text
PARTIAL history, no --accept-partial            status=CANDIDATE  candidate files=1  exit=0
PARTIAL history + COMPLETE live scan            status=CANDIDATE  candidate files=2  exit=0
```

The module's own docstring already stated the opposite rule. The guard existed and worked — on one
of the two paths evidence can arrive by.

Same commands on 1.3.1:

```text
PARTIAL history, no --accept-partial            status=PARTIAL_EVIDENCE  candidate files=0
PARTIAL history + COMPLETE live scan            status=PARTIAL_EVIDENCE  candidate files=0
```

## The rule, stated once

A finding may be promoted to `CANDIDATE` only when the **worst** quality among the evidence
**actually eligible** to support it is `COMPLETE` — or is `PARTIAL` and the caller passed
`--accept-partial`.

```text
COMPLETE   swept in full                                  may promote
PARTIAL    a file cap, an unreadable transcript, an        may promote only with --accept-partial
           oversize line — a real but bounded sample
EMPTY      nothing to sweep                                never
UNKNOWN    the record does not say how it was swept        never
           (schema 0/1 predates the field)
INVALID    a sweep ran and produced no usable session      never
```

Two halves, and the second matters as much as the first:

- **Worst, not majority.** One partial observation among nine complete ones still means part of the
  corpus was never swept. Nine neighbours cannot launder it.
- **Eligible, not everything.** `comparable()` already decides which records may support a finding:
  same scope, same workload class, compatible corpus size. A partial record belonging to another
  agent's scope, to another workload class, or dropped as non-comparable is not evidence for this
  run and does not block it. A gate that blocks on evidence a finding never used is not correct,
  it is merely stuck.

`--accept-partial` says "this bounded population is the one I meant". Nobody can say that about
evidence that is corrupt, empty, or of unestablished provenance, so it authorises `PARTIAL` and
nothing below it.

## Legacy records

A record written before schema 2 has no `evidence_quality` field, so absence proves nothing about
how that sweep was taken. It is now read as `UNKNOWN` rather than `COMPLETE`. Such records stay
readable and stay visible in reports — they simply cannot carry a promotion. Reading "not recorded"
as "fine" is the same class of error as reading a truncated log as a pass.

## What a consumer sees

`--json` gains two additive fields; no existing field changed meaning, so
`output_schema_version` stays at 1:

```json
"evidence_quality": "COMPLETE",            // unchanged: this run's live sweep alone
"effective_evidence_quality": "PARTIAL",   // new: the value that decides promotion
"partial_evidence_accepted": false         // new
```

Every finding carries the same two fields, and a candidate written from accepted partial evidence
records them in `HYPOTHESIS.md` — so the file cannot be mistaken for one built on a complete sweep.

The human report now says *why* promotion was refused and how to proceed deliberately. Exit codes
are unchanged: normal mode still exits 0, `--strict-exit` still returns the documented
`PARTIAL_EVIDENCE` code (40). The fix is that no candidate is produced, not a redesign of the exit
contract.

## Unchanged

| | |
|---|---|
| canonical skill and hooks | byte-identical to `v1.3.0` — `CANONICAL_SKILL_DELTA=0` |
| model-visible listing | unchanged — `DEFAULT_MODEL_CONTEXT_DELTA=0` |
| `TOTAL_SAVINGS` | **NOT_PROVEN** — −1.7%, 8/10 fixtures, p = 0.109 |
| `WORLD_BEST_CLAIM` | **NOT_TESTED** — no comparative benchmark was run |
| `TRUTH_RULE` | **NOT_PROMOTED** |
| observer behaviour | `carry.history()` is untouched; the append protocol and its documented cosmetic blank line are unchanged |

## Four more holes, found by adversarial review of this fix

An independent reviewer was given the diff and asked to make the patched optimizer promote evidence
that should fail closed. It found four ways, all reproduced here before being closed:

| | |
|---|---|
| a schema-1 record carrying `evidence_quality: COMPLETE` | Schema 0/1 predates the field, so such a claim comes from a hand-edited file or a migration default — not from the sweep. Any record declaring a schema older than 2 is now `UNKNOWN` whatever it asserts. |
| a retry that reported a worse sweep | The same `run_id` saying `COMPLETE` once and `PARTIAL` once was resolved in favour of the better claim, because the duplicate was dropped whole. The retry is still dropped as an observation, but its worse quality now survives on the record that remains. |
| `PARTIAL_EVIDENCE` while candidate files existed | Ledger findings count writes a hook actually denied, which no sweep bound can make partial, so they stay promotable. The status now reports what the run produced; the refused sampled evidence travels in `effective_evidence_quality` instead of being smuggled into the status word. A machine is never told `PARTIAL_EVIDENCE` while a candidate sits on disk. |
| candidates written before this release | They carry no provenance and were reported as ordinary `existing`. They are still never rewritten or deleted, but they are now named as `pre-1.3.1: no evidence provenance, re-review`. |

One reviewer finding was **not** taken: that a partial history should not demote a concentration
finding measured purely from a complete live sweep. That is true of the measurement, and the gate
here is deliberately broader — one quality for the whole run. For a patch closing a fail-open, the
conservative direction is the safe one, and `--accept-partial` is the documented way through. The
cost is stated rather than hidden: with a partial history on file, a live-only proposal waits for a
complete sweep or an explicit acceptance.

## Five more holes, found by the full independent review of this branch

The complete diff was handed to an independent adversarial reviewer, which **blocked it**. Five HIGH
findings, every one reproduced here before being accepted. Three were introduced by the first cut of
this patch; two were older holes that ran straight through the new gate.

| | what it was | where it came from |
|---|---|---|
| **H1** | a record claimed `COMPLETE` while its own counters recorded 5 unreadable files, 2 oversize lines and a file cap — and was promoted. A record with `sessions=turns=carry_bytes=0` was promoted too. | pre-existing: `valid_record()` never checked the counters |
| **H2** | a torn JSON line in a transcript was skipped silently, so a sweep that lost evidence still reported `COMPLETE`. No history needed to defeat the gate. | pre-existing: `carry.scan_full()` swallowed `json.loads` failures with no counter |
| **H3** | a candidate built from **accepted-PARTIAL** evidence was written with `effective_evidence_quality: COMPLETE` | this patch: provenance was stamped by a finding's position in a list |
| **H4** | `HOST_BEHAVIOR_SHIFT` reported status 30 and exit 40 while writing a candidate file | this patch's own invariant, broken on a path it did not cover |
| **H5** | the pre-1.3.1 artifact check was a substring search: prose satisfied it, an unreadable file counted as current, and invalid UTF-8 **crashed the run** | this patch |

Now:

- **A claim is checked against the record's own counters.** `derive_quality()` mirrors the producer's
  rule in `carry.accumulate()` — the one place that knows how a sweep went — and a record's quality
  is the worst of what it claims and what it can show. A counter that is negative, non-numeric or a
  boolean makes the record `INVALID`. A schema-2 record that shows no counters at all cannot claim
  completeness; it is `UNKNOWN`.
- **A sweep that loses a line says so.** Malformed lines are counted, degrade the sweep to `PARTIAL`,
  and travel into the history record as `malformed_lines`.
- **Provenance is attached where a finding is created**, from the evidence that created it, through
  `sampled()` and `from_ledger()`. No finding infers its source from list position.
- **One promotion gate.** A population the analyser has declared is not one world is not evidence you
  may promote from. A status that refuses promotion now leaves no candidate file behind, on every
  path.
- **Artifacts are parsed, not grepped.** `artifact_metadata()` reads the header block structurally
  and reports `PROVEN_CURRENT`, `PRE_1_3_1_REVIEW_REQUIRED` or `UNREADABLE_OR_UNVERIFIABLE`. Anything
  that cannot be read, decoded or parsed is unverifiable — never trusted, never rewritten, never
  deleted.

Three MEDIUM findings closed with them: `candidates_existing` keeps its original meaning as bare ids
(the review states moved to their own additive fields, so a consumer treating an id as an id no
longer breaks on upgrade); an unusable record can no longer become the comparability anchor and
strand a complete population; and `carry.bounded_paths()` is now the single definition of a bounded
sample, so the carry sweep and the listing scan stop measuring different files under `--max-files`.

## How it is held

A frozen 15-case matrix (A–O) and a second frozen matrix for the five blockers, both written with
their expected outcomes before the implementation; **29 mutation cases** that each go RED when the
fix they guard is reversed; a self-check that plants three corruptions in the regression harness and
requires the harness itself to fail; and the real integration path — six bounded sweeps through
`carry.py`, then `optimize.py` — asserted end to end. 645 assertions across fifteen suites.
