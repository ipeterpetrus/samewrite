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

## How it is held

A frozen 15-case matrix (A–O) written before the implementation, five mutation cases that each go
RED when the fix is reversed, a self-check that plants three corruptions in the regression harness
and requires the harness itself to fail, and the real integration path — six bounded sweeps through
`carry.py`, then `optimize.py` — asserted end to end.
