# Pre-registration: minimal-change on frozen third-party tasks, continuous endpoint

**Written and committed before this protocol had produced any run.** The output file it
names does not exist at this commit.

## Why a third run

The minimal-change sentence has now failed once under pre-registration
([the previous protocol](PREREGISTRATION_minimal_change_english.md), p = 0.0625 English /
0.125 Indonesian). Round 23 of adversarial review named two defects that make that null
hard to interpret, and this protocol fixes both:

1. **The fixtures were written by the author, who knew the hypothesis.** Positive controls
   proved the tasks were solvable without over-engineering; nothing proved they were not
   quietly suited to the instruction. This run uses tasks nobody involved wrote.
2. **The endpoint was too coarse to test.** A sign test discards ties, non-blank lines
   ranged 8-27, and a single tie raised the floor above the threshold. This run's primary
   endpoint is continuous enough that exact ties are unlikely, and its task count is large
   enough that ties would not sink it anyway.

## Tasks: MBPP, frozen by hash, selected by rule

[MBPP](https://github.com/google-research/google-research/tree/master/mbpp) (Austin et
al., 2021; CC-BY-4.0) ships 974 tasks, each with a natural-language prompt, a reference
solution and behaviour-pinning asserts — all written years before this hypothesis existed.
The file is **not vendored**; it is fetched and checked against
`sha256 ccf64ceae9c5403bf50a044cb6d505bfd2a2963ee58338ba268fd65beab92a9f`. A different
hash is a different experiment and `mbpp_select.py` refuses to run.

**Selection rule, mechanical and author-free** (`mbpp_select.py`), applied to ascending
`task_id`, taking the first 20 that pass every filter:

1. reference solution has **>= 12 non-blank lines** — the proxy for "there is room to
   over-engineer"; 120 of the 974 qualify;
2. reference solution imports **stdlib only**, so the run does not depend on what happens
   to be installed;
3. the dataset's **own tests pass on the dataset's own reference solution** — a positive
   control that costs the author no judgement at all. A task whose reference fails is
   dropped by the rule, not by opinion.

The rule reads only the reference solution and its tests. It never touches an arm, so it
returns the same twenty tasks before, during or after the study. The twenty are listed by
`python3 mbpp_select.py`.

## Arms and delivery

`plain` — the dataset prompt plus "Put it in mod.py. test_target.py must pass."
`oneline` — the same, prefixed with:

```
Make the change as small as possible; do not add abstractions that were not asked for.
```

One run per (task, arm): **40 runs**. Model `claude-haiku-4-5-20251001`, as in every prior
round. No `mode` arm; this protocol is about the sentence.

## Endpoints and tests

**Correctness gate, first and non-negotiable.** `pytest -q test_target.py` must exit 0.
A run that fails it is dropped **with its pair**. A smaller broken answer is not a smaller
answer.

**Primary endpoint: characters.** `len(mod.py.strip())` — continuous, so exact ties are
unlikely and the tie hazard that sank the previous protocol does not arise.
**Primary test:** exact paired permutation, two-sided, on the per-task proportional delta
`(oneline - plain) / plain`, over the surviving tasks. **Threshold p < 0.05.**

**Registered secondary, so it cannot be introduced later as a rescue:** the same contrast
on **non-blank lines**, by two-sided exact sign test across tasks — directly comparable to
the previous protocol's endpoint. Over 20 tasks its floor is 2/2^20, so ties cannot lift
the floor above the threshold this time.

**Also recorded, not tested:** new files created, and the reference solution's own line
count for context.

## Registered prediction

The `oneline` arm produces **fewer characters** than `plain`, two-sided exact paired
permutation p < 0.05.

## What failure means

Two pre-registered failures on independent task sets, one of them third-party, is not an
underpowered accident. If this fails, the write-up will say the minimal-change instruction
**has no demonstrated effect on solution size**, the exploratory 7-of-7 will be marked
superseded rather than merely exploratory, and the skill will drop the claim to a bare
suggestion with no evidence attached. No fourth round on a new endpoint.

## Exclusions, fixed in advance

- `rc != 0`, or the correctness gate failing, drops the **pair**.
- An empty `mod.py` in either arm drops the pair — nothing was produced to measure.
- Nothing else. Explicitly not outliers, however large.

## Stopping rule

Fixed target: **40 runs**. Incomplete for any reason — quota, outage, timeout — makes this
an **aborted study**, reported as aborted and not analysed as a smaller experiment.

## What this cannot settle

MBPP tasks are small, self-contained and single-file; a 12-line reference is room to
over-engineer but not much room. Delivery is still a prompt prefix, not the skill body.
One model. A null here bounds the effect on this class of task; it does not prove the
instruction is worthless on a large codebase.
