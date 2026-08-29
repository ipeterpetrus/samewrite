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

With `i_know=True` it loads and prints `*** EXPLORATORY — NOT CONFIRMATORY`. One file in
twenty loads without a guard: the pre-registered confirmatory run.

## Reconciliation

Every run this repo has ever scored, in one table. Nothing is dropped silently.

| bucket | n | unit | what it can support |
|---|---|---|---|
| **confirmatory** (`../confirmatory_runs.jsonl`) | **48** | runs | the conclusions. Pre-registered: one endpoint, one test, exclusions fixed in advance |
| **exploratory** (`exploratory/`) | **294** | runs | leads. Not pre-registered; fixtures and endpoints changed between rounds |
| scored A/B total | **342** | runs | the figure quoted in the repo description |
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
