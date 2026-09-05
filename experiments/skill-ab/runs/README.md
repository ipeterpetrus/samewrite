# Raw run records

Every scored run behind this repo, one JSON object per run. Paths are scrubbed
(`/home/user`, `/tmp/rig`); nothing else is altered. Each file's class, run count, unit,
arms and SHA-256 are in [`manifest.json`](manifest.json), generated from the data itself.

**The prose caveat that used to be here is now mechanical.** [`load.py`](load.py) reads the
manifest and refuses anything marked analysis-ineligible:

```
>>> load("exploratory/ab6.jsonl")
ValueError: exploratory/ab6.jsonl is exploratory, not analysis-eligible. n=48 runs,
preregistered=False. The conclusions rest on confirmatory_runs.jsonl.
Pass i_know=True to load it anyway.
```

With `i_know=True` it loads and prints `*** EXPLORATORY — NOT CONFIRMATORY`. Five files
load without a guard: the pre-registered confirmatory records, including null results.

## Frozen third-party minimal-change study

[`../mbpp_minimal_change.jsonl`](../mbpp_minimal_change.jsonl) is a completed, pre-registered
40-run study on 20 mechanically selected MBPP tasks. Its task prompts, reference solutions,
and tests predate this hypothesis; the dataset hash and selection rule are fixed in
[`../PREREGISTRATION_mbpp_minimal_change.md`](../PREREGISTRATION_mbpp_minimal_change.md).

Four pairs failed the non-negotiable correctness gate and were dropped as registered. Of
the remaining 16 pairs, `oneline` used 5,404 characters versus 6,386 for `plain` (-15.4%
pooled; mean paired proportional change -8.7%), but the primary exact paired permutation
test was **p = 0.11292**, above the pre-registered 0.05 threshold. The prediction failed.
The registered line-count secondary was also non-significant (8 smaller, 4 larger, 4 tied;
two-sided exact sign-test p = 0.38770). A directional pooled difference is not a positive
result after the registered test has failed.

## Reconciliation

Every scored A/B run is reconciled below. The original outcome experiment is retained as
its own subtotal so its 342-run figure remains comparable with earlier reports; later
pre-registered replications are listed separately rather than silently folded into it.

| bucket | n | unit | what it can support |
|---|---|---|---|
| **confirmatory** (`../confirmatory_runs.jsonl`) | **48** | runs | the conclusions. Pre-registered: one endpoint, one test, exclusions fixed in advance |
| **exploratory** (`exploratory/`) | **294** | runs | leads. Not pre-registered; fixtures and endpoints changed between rounds |
| original outcome-experiment subtotal | **342** | runs | 294 exploratory + 48 original confirmatory; the figure quoted in the repo description |
| terseness English replication (`../english_replication.jsonl`) | **32** | runs | pre-registered replication; analysed separately from the original outcome experiment |
| minimal-change replications (`../minimal_change_{en,id}.jsonl`, `../mbpp_minimal_change.jsonl`) | **88** | runs | all pre-registered; both registered minimal-change predictions failed |
| all scored A/B runs | **462** | runs | original outcome experiment plus all listed replications |
| **calibration** (`calibration/`) | **95** | runs | that fixtures fail before treatment. 81 single-arm, 14 smoke. Never an effect estimate |
| **quarantine** (`quarantine/`) | **654** | **lines, not runs** | nothing. See below |

The 654 quarantined lines are **59 run records plus 595 per-request billing rows** — two
different units. They are never pooled with each other and never counted as runs.

**These bucket rules were written after the files existed.** That is a real weakness: a
retrospective exclusion rule can be drawn where it flatters the count. The defence is not
that the rules are principled, it is that the inventory is complete — every run is in some
row above, the raw data for each row is published, and a reader who disagrees with a rule
can recompute under their own. If a bucket had been dropped rather than reclassified, no
reader could tell. That is the failure mode this table exists to prevent.

## quarantine/

A confirmatory run was accidentally launched twice; two rig processes wrote to the same
ledger concurrently.

| file | lines | unique keys | keys appearing more than once |
|---|---|---|---|
| `confirm.contaminated.jsonl` | 59 | 30 `run_id` | 29 |
| `ledger.contaminated.jsonl` | 595 | 348 `(run_id, turn)` | 247 |

**Why deduping cannot fix it.** Both processes used the same `run_id` sequence and both
produced real results, so a duplicate pair is two different executions wearing one name.
Keeping the first, the last, or the better of each pair is a selection rule invented after
seeing the outcomes — exactly the thing pre-registration exists to prevent. The files are
kept as a forensic record of a pipeline failure, not as observations. Nothing here feeds a
published number.

The run was relaunched once under `flock`, and that clean relaunch is
`../confirmatory_runs.jsonl`.

**Protocol deviation, disclosed.** The pre-registration says nothing about relaunching after
a contaminated execution — no lock, no abort rule, no contamination clause. The decision to
discard the double-launched data and rerun was therefore made *outside* the registered
protocol, after the contamination was visible. The rerun was a full re-execution of the
registered design with no parameter changed, and the discarded data is published above so
the decision is checkable rather than merely described. It remains an unregistered
deviation on the one experiment the conclusions rest on, and it is stated here rather than
left for a reader to find.

## What was checked before publishing

All 21 files were scanned for provider keys, forge tokens, bearer credentials, cloud access
ids, credential-assignment lines, private-key headers, email addresses and non-private IPv4
addresses. Zero matches, quarantine files included. Path scrubbing was the only alteration.
