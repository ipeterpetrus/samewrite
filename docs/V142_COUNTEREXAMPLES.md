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
