# The evidence loop — how SameWrite can improve without rewriting itself

SameWrite does not learn from your prompts, your code, or your reasoning. It keeps privacy-safe
aggregate measurements you already run yourself, and a small offline tool reads them and says
whether anything is strong enough to justify an experiment. Every change to what SameWrite tells a
model is written by a person and merged in a pull request.

The accurate sentence is: **accumulated evidence can identify waste patterns and propose candidate
changes, which must beat the incumbent under a pre-registered test before promotion.** Not "it gets
smarter every time you use it" — most sessions produce no new comparable evidence at all.

## The loop

```text
use SameWrite normally
        ↓
python3 tools/carry.py --history ~/logs/carry_history.jsonl     (aggregate record appended)
        ↓
python3 tools/optimize.py                                        (offline; no model, no network)
        ↓
NO_ACTION → keep working                 CANDIDATE → tools/optimize.py --emit-candidate experiments/candidates
                                                          ↓
                                           pre-register the test (experiments/*/PREREGISTRATION*.md)
                                                          ↓
                                           benchmark candidate vs incumbent, then held-out confirmation
                                                          ↓
                                           human review → pull request → merge
```

`NO_ACTION` is a successful run. The optimizer's thresholds are fixed in its source before any real
outcome was read, and a finding that does not clear its threshold is reported as insufficient
evidence rather than dressed up as a recommendation.

## What is recorded

`tools/carry.py --history` appends one aggregate record per run: schema version, SameWrite version,
timestamp, session and turn counts, carry shares and bytes-per-turn by **source label**, the
population identity (which CLI versions wrote the transcripts, which models answered), a random
`run_id`, the opaque `scope_id` and `workload_class` you passed, and the sweep's own
`evidence_quality`. The guard ledger (`SAMEWRITE_LEDGER`) records size and outcome per `Write` check.

`scope_id` and `workload_class` are written verbatim and never parsed, so they must not carry a
hostname, a username or a project name. They exist so that several agents' records can share one
file without being averaged into a population that describes nobody — see
[docs/MULTI_AGENT.md](MULTI_AGENT.md).

Never recorded: prompt text, assistant prose, source code, file contents, tool-result contents,
file names, paths, secrets, hidden reasoning. `tests/test_optimize.py` plants a canary secret in a
transcript, in the listing and in the ledger, and proves it appears in no report, no JSON, no
candidate file. The machine identity in the ledger is a short hash, not a hostname.

## What the optimizer refuses to do

- It never edits `skills/`, `hooks/`, `.claude-plugin/` or any configuration. The test hashes those
  trees around a run and fails if a byte moves.
- It never calls a model or opens a socket. The test greps its source for network and model imports.
- It never injects anything into a model's context: it is not a hook, nothing references it from the
  skill or the plugin manifest, and it runs only when you type its name.
- It never compares corpora that are not comparable (a run over one project versus the whole archive
  is a change of scope, not movement), never reports a trend from fewer than four comparable records,
  and never merges populations across a host-version change that moved the numbers.
- It never merges two scopes, never claims a direction from timestamps that cannot be ordered, and
  never turns an incomplete sweep into a candidate unless you say the bounded corpus was the target
  (`--accept-partial`). A finding is labelled `SCOPE_LOCAL`: it speaks for the population that was
  measured and for no other.

## Reading the report

```text
where cost is concentrated   the live scan, by source label
movement                     slope in percentage points per month over comparable records,
                             with a spike caution when the last value is an outlier
population                   runtimes and models; GLOBAL_SIGNAL / MODEL_SPECIFIC_SIGNAL /
                             INSUFFICIENT_DATA, and HOST_BEHAVIOR_SHIFT when the host changed
candidates                   what cleared its threshold, and the experiment it implies
policy mutation              always NONE
```

A valid run exits 0, including `NO_ACTION`; `--strict-exit` maps the status to the exit code for a
scheduler. `--json` prints the same aggregates for scripting. `--emit-candidate DIR` writes one
`HYPOTHESIS.md` per candidate: observation, hypothesis, incumbent, primary metric, correctness and
safety gates, instruction budget, risk, benchmark required, promotion criterion. Those files are
specifications for a human, not instructions for a model. Each lands in its own directory directly
under `DIR`: an ordinary candidate id is the directory name, and an id whose scope holds a path
separator or a dot segment is stored as `candidate-sha256-<digest of the id>` — the logical id is
still what `--json` reports and what the file itself states. A candidate that cannot be stored
inside `DIR` is refused and reported, never written elsewhere.

## Why it must stay this shape

An optimizer that rewrote the skill after every task would change the thing being measured while
measuring it, grow the always-on text it is supposed to shrink, and give every user a different
undocumented policy. The value of this repository is that its claims are reproducible; a
self-modifying runtime would end that. So the loop stops at a candidate, and a person decides.
