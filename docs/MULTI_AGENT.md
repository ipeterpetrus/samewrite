# Many agents, running all the time

SameWrite's measurement layer was built for one person on one machine. Nothing about that is wrong,
but a population of agents breaks assumptions a single user never notices: two agents produce the
same numbers on the same day and are not the same observation; a reviewer's transcripts and a
builder's transcripts averaged together describe nobody; a scheduler that calls the optimizer every
hour rewrites the same proposal forever; a sweep that silently hit a file cap looks exactly like a
sweep of the whole world.

This document is the generic contract. It has nothing to do with any particular deployment;
`docs/AI_VOS_PROFILE.md` is one thin profile on top of it, and it adds no mechanism of its own.

## Scope is the unit of comparison

A **scope** is the population a record belongs to: one agent, one role, one profile, one machine —
whatever you decide, as long as the label is stable and low-cardinality.

```bash
python3 tools/carry.py --history ~/state/carry_history.jsonl \
        --scope-id builder-07 --workload-class build
python3 tools/optimize.py --history ~/state/carry_history.jsonl --scope-id builder-07
```

`scope_id` is opaque: it is written verbatim into the record and never parsed, so it must not carry
a hostname, a username, a project name or anything else you would not paste in public. Records from
different scopes are counted, named and kept apart; they are never averaged. Without `--scope-id`
the optimizer analyses the newest scope in the history and *names* the others rather than merging
them.

`workload_class` is the second axis, and it exists because the most common false trend is not a
regression at all: the work changed. A scope whose workload class changes mid-history is reported
as `WORKLOAD_SHIFT`, and the records on either side of the change are not compared.

Findings carry `scope_claim: SCOPE_LOCAL`. A candidate derived from one scope is a statement about
that scope, and the specification says so in its own text, because the cheap misreading of
"this listing entry is never used" is "uninstall it for everyone".

## Identity, duplicates and merging

Each record carries `run_id`, a random 128-bit value. It is the **only** dedup key.

- Two agents that produce an identical timestamp, turn count and carry share are two observations.
  Collapsing them by value would quietly shrink the population being measured.
- A retried or re-copied write of the same record is one observation. Copying several machines'
  history files together, or running the same `rsync` twice, is therefore idempotent.

That makes the history file mergeable: concatenate any number of hosts' files in any order. Order
does not matter, because time ordering is validated separately and never assumed.

## Time is not trusted

Clocks in a fleet disagree, drift and jump. Before any trend is computed, the record order is
classified:

| order | meaning | what is reported |
|---|---|---|
| `ok` | timestamps strictly increase | a trend may be computed |
| `reversed` | a timestamp went backwards | `TREND_AMBIGUOUS`; no direction is claimed |
| `ambiguous` | every record shares one timestamp | `TREND_AMBIGUOUS`; no direction is claimed |

No wall-clock comparison decides anything else. The optimizer does not schedule, expire or rotate
anything by time.

## Evidence quality, and failing closed

Every sweep labels its own completeness, and the label travels with the record:

| quality | when | effect |
|---|---|---|
| `COMPLETE` | every transcript read, no oversized lines, no file cap | candidates may be emitted |
| `PARTIAL` | unreadable files, oversized lines skipped, or `--max-files` hit | **no candidate** from live evidence unless `--accept-partial` |
| `INVALID` | files were scanned and nothing usable came out | no findings at all |
| `EMPTY` | nothing to scan | no findings at all |

`--accept-partial` exists for the honest case where a bounded corpus *is* the target ("the last 200
sessions"), and it says so in the output. It is not a way to get a candidate out of a broken sweep:
the quality label is still recorded and still printed.

## A scheduler may call this every cycle

The optimizer is a plain command. There is no daemon, no timer, no background process, and it
installs nothing — put it in cron, in a systemd timer, in your own loop, or run it by hand.

Two properties make repeated invocation safe:

- **Deterministic candidate identity.** A candidate's id is `{finding}-{scope}-{digest}`, where the
  digest covers the finding, the scope, the threshold schema version and the *bucket* the evidence
  falls in (5 percentage points wide). Evidence that wobbles inside a bucket produces the same id
  and the existing specification is left untouched (`EXISTING_CANDIDATE`). Evidence that genuinely
  moves produces a new id and a new file.
- **Reentrancy.** Candidate emission takes a non-blocking `O_CREAT|O_EXCL` lock. A second
  invocation that arrives mid-write exits `ALREADY_RUNNING` instead of interleaving. Read-only
  analysis takes no lock and never blocks.

Specifications are written to a temporary file, `fsync`ed and `os.replace`d, so a crash leaves
either the old file or the new one.

## Exit codes and the machine contract

A valid run exits `0`, including `NO_ACTION` — a scheduler must not read "nothing to do" as
breakage. `--strict-exit` maps the status to the exit code instead:

| status | code | meaning |
|---|---|---|
| `NO_ACTION` | 0 | nothing cleared its threshold |
| `CANDIDATE` | 10 | at least one candidate |
| `INSUFFICIENT_DATA` | 20 | not enough comparable evidence yet |
| `HOST_BEHAVIOR_SHIFT` | 30 | the host changed under the records; they are not one population |
| `PARTIAL_EVIDENCE` | 40 | the sweep was incomplete and partial evidence was not accepted |
| `ALREADY_RUNNING` | 41 | another invocation holds the emission lock |
| `INTERNAL_ERROR` | 50 | unexpected |

`--json` carries `output_schema_version` (the shape) and `threshold_schema_version` (the numbers).
They move independently: a threshold change is a decision that must be argued for, and every
emitted candidate records which threshold version produced it.

## Concurrency and durability

- **Writers.** One record is a single `write()` of well under `PIPE_BUF`; Linux serialises appends
  to a regular file. Measured at 32 and 64 concurrent writers: every line intact, every `run_id`
  distinct, zero rejects.
- **Crash.** A machine that dies mid-append leaves a line without a newline. The reader rejects
  exactly that line and counts it. The writer checks for a missing trailing newline before
  appending, so the *next* record is not glued to the fragment — otherwise one crash would destroy
  two records instead of one.
- **Size caps.** A transcript line above 8 MB is skipped and counted (and turns the sweep
  `PARTIAL`); a history record above 1 MB is not appended at all, because a giant partial line is
  the one shape a concurrent append could actually tear.

## Resource budget (pre-registered)

Measured on this machine with `experiments/scale/scan_scale.py`, synthetic archives of 60-turn
sessions:

| archive | on disk | full sweep | peak RSS | bounded to 200 files |
|---|---|---|---|---|
| 1,000 sessions | 75 MB | 1.2 s | 13 MB | 0.23 s |
| 10,000 sessions | 751 MB | 12.4 s | 13 MB | 0.24 s |

Scaling is linear (10x the corpus costs 10.5x the time) and memory is flat, because the sweep
streams and never holds a transcript.

The decision rule was fixed **before** those numbers were read: build an incremental index only if a
full sweep of 10,000 sessions exceeds 120 s or 512 MB RSS. It does neither, by an order of
magnitude, so there is no index. That is deliberate: an index is a second piece of persistent state
that can go stale against a rewritten transcript, be corrupted, or be invalidated wrongly — failure
modes a stateless sweep does not have. Bounded mode (`--max-files`) covers the case where you want
a fixed cost per cycle, and it marks its evidence `PARTIAL` so a bounded sweep is never mistaken for
the whole population.

## What does not change under any of this

Zero bytes reach a model. The optimizer is not a hook, no skill or manifest references it, and the
policy surface — `skills/`, `hooks/`, `.claude-plugin/` — is byte-identical to the released
`v1.1.0` tag. Everything above is measurement and reporting; the only thing it can produce is a
file a person reads.
