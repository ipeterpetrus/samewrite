# SameWrite 1.2.0 — release notes

**One sentence.** The skill is byte-for-byte what 1.1.0 shipped; everything in this release is the
measurement layer learning to survive a population of agents that never stops — several roles, tens
of parallel writers, crashes, clock skew, bounded sweeps and a scheduler calling it every cycle.

**Nothing a model reads has changed.** `skills/samewrite/SKILL.md`, `skills/edit-discipline/SKILL.md`
and every hook are byte-identical to the `v1.1.0` tag; the only file in the always-on surface that
differs is the version string in the plugin manifests. If you use SameWrite from one machine, this
release changes nothing for you except three new flags you will never type.

## What is new

- **Scope isolation.** `tools/carry.py --scope-id <label> --workload-class <label>` records which
  population a run belongs to, and `tools/optimize.py --scope-id` analyses exactly one. Records from
  different scopes are counted, named and kept apart — never averaged into a population that
  describes nobody. A change of workload class inside one scope is reported as `WORKLOAD_SHIFT`, not
  as a trend, because the most common false regression is that the work changed.
- **Findings are scope-local by construction.** Every finding carries `scope_claim: SCOPE_LOCAL`, and
  the two candidates this tool actually produces now carry the invariant that makes them safe, in
  the specification file itself rather than only in documentation:
  - listing prune — *a listing entry cold in one role can be essential to another; this is about
    reducing exposure in this scope, never an instruction to uninstall anything globally*;
  - output shaping — *never truncate the only copy of evidence; for security, governance, build
    validation, destructive operations and any failure path, the raw record must survive*.
- **Evidence quality, failing closed.** A sweep labels itself `COMPLETE`, `PARTIAL`, `INVALID` or
  `EMPTY`, and the label is written into the record. A `PARTIAL` sweep cannot produce a candidate
  unless `--accept-partial` says the bounded corpus was the intended target — and it still prints
  the label either way.
- **Opaque run identity.** Each record carries a random `run_id`, and that is the only dedup key.
  Two agents producing identical numbers are two observations; a retried or re-copied write is one.
  History files from any number of hosts can therefore be concatenated in any order, twice, safely.
- **Time is never trusted.** Record order is classified `ok` / `reversed` / `ambiguous`, and a trend
  is computed only for `ok`. Skewed or identical clocks yield `TREND_AMBIGUOUS` and no direction.
- **Safe to schedule.** Candidate ids are deterministic (`finding-scope-digest`, the digest covering
  the threshold version and a 5-point evidence bucket), so evidence that wobbles rewrites nothing
  (`EXISTING_CANDIDATE`) and evidence that genuinely moves opens a new file. Emission takes a
  non-blocking exclusive lock (`ALREADY_RUNNING` rather than interleaving) and writes through
  `fsync` + `os.replace`. There is no daemon and nothing is installed: use cron, a timer, or your
  own loop.
- **A machine contract.** A valid run exits `0` including `NO_ACTION`; `--strict-exit` maps status to
  exit code. `--json` carries `output_schema_version` and `threshold_schema_version` separately, and
  every emitted candidate records which threshold version produced it.
- **Bounded mode.** `--max-files N` caps the sweep cost per cycle, takes the **most recent** N
  transcripts, records how many were skipped and marks the evidence `PARTIAL`.
- **Pathological input.** A transcript line above 8 MB is skipped and counted (turning the sweep
  `PARTIAL`); a history record above 1 MB is not appended at all; control bytes in a source label
  are stripped in one place before they can reach a terminal, a JSON file or a specification.

## Two defects found and fixed at the root

- **A crash destroyed two records, not one.** A machine dying mid-append leaves a line with no
  newline; the next writer appended straight onto the fragment, so the torn record took a good one
  with it. The writer now checks for the missing newline first. Proved by mutation: revert the check
  and the oracle goes red.
- **A bounded sweep sampled the wrong end of the archive.** `--max-files` took the first N paths as
  listed, which in a long-lived archive is the oldest and least informative slice. It now takes the
  N most recently modified. Caught on real data, not in theory: the first bounded run over a real
  archive returned `INVALID` evidence because all 60 files it picked predated the turn floor.

## Measured

| archive | on disk | full sweep | peak RSS | bounded to 200 files |
|---|---|---|---|---|
| 1,000 sessions | 75 MB | 1.2 s | 13 MB | 0.23 s |
| 10,000 sessions | 751 MB | 12.4 s | 13 MB | 0.24 s |

Scaling is linear (10× the corpus costs 10.5× the time) and memory is flat. The decision rule was
fixed before those numbers were read: build an incremental index only if a full sweep of 10,000
sessions exceeds 120 s or 512 MB RSS. It does neither by an order of magnitude, so **there is no
index** — a stale or corrupt index is a failure mode a stateless sweep does not have.

Against the released 1.1.0 parser on the same 1,000-session corpus, the hardened sweep costs
**+4%** wall time (1.10 s → 1.14 s, best of three) at identical memory and identical results. That
is the price of the line cap and the provenance counters, and it is stated rather than hidden.

## Gate

```text
POLICY_SURFACE_UNCHANGED=PASS     skills/ and hooks/ byte-identical to v1.1.0 (sha256 per file);
                                  .claude-plugin/ differs only in the version string
ZERO_CONTEXT_OVERHEAD=PASS        optimize.py referenced by no skill, hook or manifest
SCOPE_ISOLATION=PASS              cross-scope and cross-workload merges refused and reported
ROLE_MATRIX=PASS                  BUILDER / REVIEWER / OPS / RESEARCH: no shared candidate id
CONCURRENCY=PASS                  32 and 64 parallel writers: every line intact, every run_id distinct
CRASH_CONSISTENCY=PASS            torn tail rejected alone; the next append survives
REENTRANCY=PASS                   second scheduler refused, no partial files, no .tmp residue
FAIL_CLOSED_ON_PARTIAL=PASS       incomplete sweep cannot produce a candidate
CLOCK_INDEPENDENCE=PASS           reversed and identical timestamps claim no direction
DETERMINISTIC_CANDIDATES=PASS     same evidence bucket → same id → EXISTING_CANDIDATE
ZERO_NETWORK=PASS                 static grep, in-process socket denial, and the whole suite green
                                  in containers run with --network none
PRIVACY=PASS                      canary in a transcript, a listing and the ledger: absent from
                                  report, JSON and candidate files
NO_AUTOMATIC_MUTATION=PASS        skills/, hooks/, .claude-plugin/ hashed around a run
TESTS=PASS                        400 assertions in eleven suites, clean python:3.9-slim and
                                  python:3.12-slim, offline
MUTATION=PASS                     10 invariants: each goes RED when its implementation is broken
                                  and GREEN against the real source
```

## Known limitations

Every number above is from one machine's synthetic and local corpora; no other host's data has been
seen. The 5-point evidence bucket is a judgement, not a measured optimum — it is versioned so that
changing it is a decision with a paper trail. The scheduler contract has been tested with four
concurrent emitters, not with a real fleet running for weeks. And the optimizer still proposes
nothing that anyone has promoted: both candidates from 1.1.0 remain unimplemented and unmeasured.

## Not in this release

No tag, no GitHub release, no merge. Nothing self-modifies, nothing self-promotes, and the
optimizer holds no Git or GitHub authority.
