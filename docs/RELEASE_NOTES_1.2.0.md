# SameWrite 1.2.0 — release notes

**One sentence.** The skill is byte-for-byte what 1.1.0 shipped; everything in this release is the
measurement layer learning to survive a population of agents that never stops — several roles, tens
of parallel writers, crashes, clock skew, bounded sweeps and a scheduler calling it every cycle.

**Released for the evidence layer, not for a savings number.** The end-to-end token question came
back `NOT_PROVEN` and stays that way in public. What is measured and does hold: zero added
model-context bytes, quality non-inferior on every gate, Hermes skill support verified, and two of
the optimizer's own candidates rejected on their own evidence.

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

## Hermes Agent: verified

SameWrite's canonical skill is loaded by **Hermes Agent 0.21.3** (`NousResearch/hermes-agent`,
commit `1ad89ac`) without transformation. Verified in an isolated profile with no API key set —
installed, discovered, listed, loaded, invoked, uninstalled; 11/11 checks
(`experiments/hermes/acceptance_hermes.py`).

| measured on Hermes | value |
|---|---|
| unused skill, cost in the system prompt | **80 B** |
| unused skill, body bytes in context | **0** — progressive loading is real |
| loaded on demand | 4,503 B |

One host difference is handled mechanically rather than ignored: Hermes truncates a skill
description to 60 characters in its system prompt, and the canonical description is 391. Shipping
the canonical file unchanged would silently lose its routing tail exactly where routing happens, so
`tools/adapters.py` generates a Hermes target whose **body is byte-identical** and whose
description is 49 characters. CI fails on drift.

Claude Code's hooks are Claude-specific and are **not** installed into Hermes. The observer and
optimizer run there — they are ordinary offline Python — but they have no reader for Hermes session
files, so they measure nothing and are labelled `UNTESTED` rather than supported.

## The two strongest candidates, and why neither shipped

Full evidence in [docs/CANDIDATES.md](CANDIDATES.md).

- **`bash-output-shaping` — REJECTED.** Bash is 62% of carry, so bounding it looked like the best
  available change. Measuring 30,731 real Bash results ended it: median 449 B, p90 2,246 B,
  **maximum 28,989 B, and not one above 30 kB**. The host already caps Bash output and spills the
  remainder to a file. Bash dominates carry by *accumulation across thousands of small results*,
  not by size — a different problem, and a rule shaped for the wrong one would have cost always-on
  bytes and bought nothing.
- **`listing-prune` — DEFERRED.** The measurement is real: 70 of 82 listing entries were never
  invoked, 24,002 B, 80% of the listing. But that is **2.30% of total carry**, below the
  `NEGLIGIBLE` threshold fixed before the numbers were read and far below this rig's measured
  noise; the cold entries belong to *other* plugins, not to SameWrite; and an entry cold in one
  role can be essential to another. It ships as a recommendation you can run yourself
  (`python3 tools/skills.py --markdown`), which is a legitimate outcome rather than a fallback.

## Measured on AI-VOS-shaped work: NOT_PROVEN, and the reason is worth more than a number

200 model runs on `claude-opus-5` across ten role-shaped fixtures (builder, reviewer, ops,
governance, research), pre-registered in `experiments/aivos/PREREGISTRATION.md` before the first
run existed. Full write-up: [experiments/aivos/RESULTS.md](../experiments/aivos/RESULTS.md).

**Every quality gate is non-inferior** — correctness, safety, evidence completeness and authority
compliance. Zero baited destructive commands executed. Zero files written by a role forbidden to
write. **Observer isolation passed**: zero observer artefacts in 80 transcripts, and a sentinel
value placed in the environment was proved not to reach the model at all.

**The cost verdict is `NOT_PROVEN`, and the experiment explains why rather than shrugging.** The
skill file is byte-identical at 1.1.0 and 1.2.0, so two arms in the matrix present the model with
the same bytes — which turns them into a measurement of the rig's own noise. Three such
null-vs-null comparisons read **−5.6%**, **+15.1%** and **−6.4%**. The middle one reached
**p = 0.021** between treatments that cannot differ, and did not replicate. The candidate was
cheaper than bare on 8 of 10 fixtures (p = 0.109) with a median of −1.7%, which is smaller than
that noise.

Two methodological defects were found and fixed in the process, and both are the kind that
manufacture results:

- **arm was perfectly confounded with wall-clock time** in the first matrix (jobs submitted
  arm-major drain in blocks), which alone produced a 15% "difference" between identical arms;
  fixed by randomising run order under a recorded seed;
- **the second-channel rig scored a quota wall as a model failure** — ten `INFRA_ERROR` runs
  reported as "0/5 correct". Fixed; the GPT-5.6 Sol channel is reported as `UNTESTED`, never
  estimated from the Claude numbers.

## Two defects found and fixed at the root

- **Proposal churn from a settling estimator.** A trend candidate's identity was bucketed on the
  *magnitude* of the fitted slope. A slope fitted over a growing window decays even when the world
  stops moving, so each decay step crossed a bucket and minted a new proposal: 39 new files during
  a plateau in which nothing changed. Identity is now the *direction*, so one sustained movement is
  one proposal and a reversal is a new one. A 30-day, 9,000-invocation simulation now produces
  **zero** new proposals in its settled tail.
- **The same movement reported twice.** A share vector sums to 100, so one source rising *is*
  another falling. The optimizer emitted both as independent candidates, doubling every proposal
  for zero information. The complement is now named inside the surviving finding's evidence instead
  of opening a second file.
- **An evidence rule that would have preserved a leak.** The invariant said raw evidence must
  survive, with no exception — which would have kept a credential verbatim and called it an
  archive. Reading a real governance contract found the omission. Secret material is now carved
  out explicitly, in the specification text a builder actually reads.
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
TESTS=PASS                        415 assertions in eleven suites, clean python:3.9-slim and
                                  python:3.12-slim, both run with --network none
MUTATION=PASS                     12 invariants: each goes RED when its implementation is broken
                                  and GREEN against the real source
HERMES_SKILL=VERIFIED             Hermes Agent 0.21.3 (1ad89ac), isolated profile, 11/11
HERMES_OBSERVER=UNTESTED          runs there; no reader for Hermes session files
CORRECTNESS=NON_INFERIOR          80 runs, four arms, ten role-shaped fixtures
SAFETY=NON_INFERIOR               zero baited destructive commands executed
EVIDENCE_COMPLETENESS=PASS        governance fixtures require verbatim identifiers
AUTHORITY_COMPLIANCE=PASS         zero writes by a role forbidden to write
SAVINGS_CLASS=NOT_PROVEN          effect smaller than the measured null-vs-null noise
BASH_CANDIDATE=REJECTED           duplicated by platform behaviour; 30,731 results measured
LISTING_CANDIDATE=DEFERRED        2.30% of carry, below the pre-set floor; user configuration
SOL_CHANNEL=UNTESTED              10/10 INFRA_ERROR, account usage limit; never estimated
```

## Known limitations

Every number above is from one machine's synthetic and local corpora; no other host's data has been
seen. The 5-point evidence bucket is a judgement, not a measured optimum — it is versioned so that
changing it is a decision with a paper trail. The scheduler contract has been tested with four
concurrent emitters, not with a real fleet running for weeks. And the optimizer still proposes
nothing that anyone has promoted: both candidates from 1.1.0 remain unimplemented and unmeasured.

## What this release does not claim

**Overall token-cost improvement: NOT_PROVEN.** The observed effect was −1.7%, cheaper on 8 of 10
fixtures (p = 0.109), and the rig's own measured null-vs-null variance is larger than that. No
percentage saving is claimed anywhere, and none should be quoted from this release.

`GPT-5.6 Sol` portability: **UNTESTED** — the attempt returned 10/10 infrastructure errors on an
account usage limit, and an untested channel is never estimated from a tested one. The Hermes
observer is **UNTESTED**: it runs there, but it has no reader for Hermes session files, so it
measures nothing. Hermes *skill* support is VERIFIED; that is a different claim and the two are
kept apart deliberately.

Nothing self-modifies and nothing self-promotes. The optimizer holds no execution, Git, GitHub,
promotion or owner authority, and a candidate reaches the codebase only when a person opens a pull
request.
