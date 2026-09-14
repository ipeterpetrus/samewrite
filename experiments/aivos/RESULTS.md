# AI-VOS role matrix — results

Pre-registration: [PREREGISTRATION.md](PREREGISTRATION.md), written before the first run existed.
Nothing below changes a threshold, a gate or a classification rule that file fixed in advance.

**Headline: `SAVINGS_CLASS = NOT_PROVEN`, every quality gate `NON_INFERIOR`, observer isolation
`PASS`.** The most useful thing this experiment produced is not a cost number. It is a measurement
of how much of a cost number this design can trust, and the answer is: less than the effect being
looked for.

## What was run

| | |
|---|---|
| model | `claude-opus-5`, CLI 2.1.270 |
| fixtures | 10, two per role shape (builder, reviewer, ops, governance, research) |
| arms | A bare · B SameWrite 1.1.0 · C SameWrite 1.2.0 candidate · D = C + observer already run |
| runs | 80 per matrix (4 arms × 10 fixtures × 2 reps), twice, plus a 40-run replication of one null pair — 200 model runs |
| excluded | 0 — no `INFRA_ERROR`, no row with `treatment_ok=false` |

`skills/samewrite/SKILL.md` is byte-identical at `v1.1.0` and at the candidate
(`sha256 d7c65ee5a4496263` both). **Arms B and C therefore present the model with the same bytes**,
which is what makes the B-vs-C comparison a measurement of this rig's own noise rather than an
assumption about it.

## Two methodological defects found, in order of severity

### 1. Arm was perfectly confounded with wall-clock time

The first 80-run matrix built its job list arm-major. A thread pool drains submissions in order, so
all A runs finished before B, all B before C, and so on — mean completion index **9.5 / 29.5 / 49.5
/ 69.5** for A/B/C/D. Every drift in server load, cache state or rate limiting across the half-hour
run mapped directly onto an "arm difference".

That run reported a **+15.1% gap between the two byte-identical arms**. It was an artefact of the
schedule. Fixed by randomising job order under a recorded seed (`--seed`, stored in every row); the
same comparison then read **−5.6%**.

This is why the first matrix is kept in the repository next to the second. A result that changes
when you fix the ordering is a result that was never about the treatment.

### 2. At n = 10 this design produces a significant result between identical treatments

The randomised matrix contains **two** pairs of byte-identical arms, because the observer writes
nothing into the model's context: B–C (same skill file) and C–D (same skill file; D differs only by
a state directory on disk and one environment variable).

| comparison | treatments | median | cheaper on | sign test |
|---|---|---|---|---|
| C vs B | identical | −5.6% | 6/10 | p = 0.754 |
| **C vs D** | **identical** | **+15.1%** | **1/10** | **p = 0.021** |

The second one crosses the pre-registered α = 0.05. It is a false positive, and that is a
conclusion rather than an excuse, because it was checked three separate ways.

**The treatments are provably the same.** The skill directories are byte-identical copies; the only
difference is `SW_OBSERVER_STATE` in the environment and a state directory outside both the config
directory and the working directory. A direct probe put a sentinel value in that environment
variable and it appears **nowhere** in the resulting transcript — an environment variable does not
reach the model. The automated leak check found zero observer artefacts in all 80 transcripts.

**It did not replicate.** The same pair was re-run, 40 fresh runs, different seed:

| run | C vs D | cheaper on | sign test |
|---|---|---|---|
| randomised matrix | **+15.1%** | 1/10 | **p = 0.021** |
| replication, seed 777 | **−6.4%** | 6/10 | p = 0.754 |

It changed sign and lost significance. Three null-vs-null measurements now exist between arms that
cannot differ — −5.6%, +15.1%, −6.4% — so this rig's run-to-run spread is roughly ±6% with
excursions past 15%, and one of those excursions reached p < 0.05 on its own.

Five comparisons at α = 0.05 give roughly a 23% chance of at least one false positive before any
effect exists. Here one landed on a pair that cannot possibly differ. **Any single p < 0.05 from
this design, in either direction, is unconfirmed until it replicates** — including one that would
have flattered SameWrite.

## Quality gates — evaluated before any cost number

| arm | runs | correct | safety | evidence complete | authority respected |
|---|---|---|---|---|---|
| A bare | 20 | 16 | 20 | 20 | 20 |
| B 1.1.0 | 20 | 17 | 20 | 20 | 20 |
| C 1.2.0 | 20 | 17 | 20 | 20 | 20 |
| D + observer | 20 | 17 | 20 | 20 | 20 |

Zero safety violations: no baited destructive command was executed in any run. Zero authority
violations: no run wrote a file in a role whose fixture forbids writing — including the runs that
answered incorrectly. Zero evidence failures on the governance fixtures, which require exact
identifiers to be reproduced verbatim.

Correctness by role shape is flat except where both arms are flat together: builder, reviewer and
governance are 4/4 in every arm; ops and research are where every arm loses runs, which says the
fixtures are hard rather than that a treatment helped or hurt.

## Cost

| comparison | median | cheaper on | sign test | class |
|---|---|---|---|---|
| C vs B (identical treatments) | −5.6% | 6/10 | p = 0.754 | noise floor |
| C vs D (identical treatments) | +15.1% | 1/10 | p = 0.021 | **false positive — did not replicate** |
| C vs D (identical treatments, replication) | −6.4% | 6/10 | p = 0.754 | noise floor |
| B vs A | −0.7% | 5/10 | p = 1.000 | NOT_PROVEN |
| C vs A | −1.7% | 8/10 | p = 0.109 | NOT_PROVEN |
| D vs A | +8.3% | 2/10 | p = 0.109 | NOT_PROVEN |

The candidate is cheaper than bare on 8 of 10 fixtures, which is a consistent direction and is
**not** significant at this n — 8/10 gives p = 0.109, and the pre-registration said in advance that
only 9/10 or better can reach p < 0.05 here. The median effect (−1.7%) is also smaller than the
measured noise between identical arms (−5.6%), which the pre-registration independently says forces
`NOT_PROVEN`.

Both rules point the same way, so the verdict does not depend on which one you prefer.

## What this does and does not license anyone to say

**Supported:**

- On these ten AI-VOS-shaped fixtures with Opus 5, SameWrite 1.2.0 is non-inferior to bare on
  correctness, safety, evidence completeness and authority compliance.
- The observer costs the model nothing: zero artefacts in 80 transcripts, and an environment
  variable does not reach the model.
- SameWrite 1.2.0 and 1.1.0 present the model with identical bytes, verified by hash.

**Not supported, and not to be written anywhere:**

- Any percentage saving on this workload. The honest statement is `NOT_PROVEN`.
- Any claim that SameWrite is *not* cheaper. A null at n = 10 is `INSUFFICIENT_DATA`, not evidence
  of absence; the direction was consistent on 8 of 10 fixtures.

## The second model channel: UNTESTED, and why that word

The pre-registration named two channels. The Claude channel ran. The Sol channel
(`gpt-5.6-sol` via Codex CLI 0.153.2) did not, and the reason is recorded rather than smoothed
over: **all 10 runs returned the CLI's own "You've hit your usage limit", 10/10 `INFRA_ERROR`.**
The account's session quota was exhausted partway through this session's work.

Two things were done about it, and neither is "estimate it from the Claude numbers".

1. **The channel is reported as `UNTESTED`.** Not passing, not failing, not inferred. A model
   result that was never produced does not get a number.
2. **The harness defect it exposed was fixed.** The first version of `rig_sol.py` scored those ten
   quota walls as `FAIL` — "0/5 correct" for both arms — which is exactly the failure this
   repository already has a rule against, reappearing in new code. `classify_infra()` now matches
   the CLI's own error text and excludes such runs, and the summary refuses to print a channel
   result when nothing was scorable. Reproduce the corrected behaviour with
   `python3 experiments/aivos/rig_sol.py`.

Worth stating plainly, because it is the more interesting half: a rig that had not separated
infrastructure failure from model failure would have published "SameWrite scores 0/5 on GPT-5.6
Sol". That number would have been entirely fictional and entirely believable.

## What would settle it

More paired fixtures, not more repetitions — repetitions inside a fixture do not add n. A design
that could detect a 5% effect against a noise floor of this size needs roughly 40–60 paired
fixtures, or a cost metric with less run-to-run variance than end-to-end token count. Neither is a
reason to delay a release whose gate is correctness, and both are written down here so the next
person does not have to rediscover them.

## Reproduce

```bash
python3 experiments/aivos/fixtures_aivos.py                     # the fixtures and their oracles
python3 experiments/aivos/rig_aivos.py --arms A,B,C,D --repeat 2 \
        --model claude-opus-5 --seed 20260915 --out runs/matrix.jsonl
python3 experiments/aivos/analyze_aivos.py runs/matrix.jsonl
python3 experiments/aivos/longrun.py                            # 30 days, no model needed
python3 experiments/aivos/bash_residue.py --max-files 400       # the Bash candidate's evidence
```
