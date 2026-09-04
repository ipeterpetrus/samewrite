# Pre-registration: the minimal-change sentence, in English, with enough tasks to test it

**Written and committed before any run of this protocol existed.** The data files named
below do not exist at this commit. That ordering is checkable in the git history.

## Why this run exists

Two gaps, both found by adversarial review rather than by the author.

**Gap 1 — the result is exploratory and has been quoted as if it were not.** The
minimal-change finding (*fewer non-blank lines in 7 of 7 pairs, p = 0.016*) comes from
`runs/exploratory/ab8.jsonl`, which `manifest.json` classifies `exploratory`,
`preregistered: false`. The skill file has been printing it beside the terseness result,
which *is* confirmatory, without saying which is which. This run is the first
pre-registered test of the claim.

**Gap 2 — one language, and a task count too small to carry a claim.** Round 22
established that four fixtures repeated N times give four observations of "a task", and
that a two-sided sign test over four tasks has a floor of 2/2⁴ = 0.125 — it cannot reach
0.05 whatever the data show. Adding repeats does not help; adding **tasks** does. This
protocol uses **six**, whose floor is 2/2⁶ = **0.031**, so the registered test can
actually reject.

## Fixtures

The four from round 8 (`csv_report`, `rate_limiter`, `retry_backoff`, `plugin_registry`)
plus two written for this protocol, before any run:

- `config_merge` — merge two nested config dicts, right wins, nested dicts merge rather
  than replace, neither input mutated. Minimal solution: **8 non-blank lines**.
- `path_router` — match a path against a segmented pattern with `<name>` captures, return
  the captures or `None`. Minimal solution: **12 non-blank lines**.

Both were given the **positive control before any agent ran**: the minimal solution above
was written by hand and `pytest` passed on it, so the fixtures can be cleared without
over-engineering. A fixture whose tests can only be satisfied by a large solution would
measure nothing.

## Hypothesis and prediction

**H1.** A one-sentence minimal-change instruction reduces the size of the produced
solution when the whole prompt surface is English, as it did in Indonesian.

**Primary endpoint.** Non-blank lines in `mod.py` after the run, **conditional on the
correctness gate**: `pytest -q test_target.py` must exit 0. A run that does not pass is
not a smaller solution, it is a broken one.

**Primary test.** Two-sided exact sign test across the **six tasks** — per task, the sum
of non-blank lines over its repeats, in each arm. Task is the unit because task is what
the claim generalises over.

**Registered prediction.** The `oneline` arm produces fewer lines than `plain` on the
task-level test, two-sided p < 0.05.

**Secondary, registered here so it is not post-hoc later.** (a) the same contrast at run
level, reported as valid only for these six fixtures; (b) a language-interaction test —
per-task proportional deltas, English minus Indonesian, two-sided exact sign test over the
six tasks. A non-significant interaction will be reported as "the data do not support
claiming the magnitudes differ", never as "the magnitudes are equal".

**What failure means.** If the task-level prediction fails, the minimal-change result does
not replicate in English at this task count, the exploratory 7-of-7 stands as exploratory
only, and the skill file must say so. No rescue round, no switch to a different endpoint,
no dropping a task.

## Design

- **Arms:** `plain` and `oneline`. The `mode` arm (the 5,228-byte block) is out of scope:
  its Indonesian result already failed to beat the sentence, and this protocol is about
  whether the sentence itself travels.
- **Languages:** English (primary) and Indonesian (for the interaction). Both get all six
  fixtures, so the interaction has six tasks rather than four.
- **Repeats:** 2 per (task, arm, language). 6 x 2 x 2 x 2 = **48 runs**.
- **Model:** `claude-haiku-4-5-20251001`, as in every prior round.

## The strings

```
id : Buat perubahan sekecil mungkin; jangan menambah abstraksi yang tak diminta.
en : Make the change as small as possible; do not add abstractions that were not asked for.
```

The English sentence is a faithful translation of the Indonesian one that was measured,
not a rephrasing.

## Exclusions, fixed in advance

- A run with `rc != 0`, or that fails the correctness gate, is dropped **together with its
  pair**. Both arms must have produced working code for the size comparison to mean
  anything.
- If a whole task loses every pair in a language, that task is reported as lost, not
  silently omitted from the denominator.
- No other exclusion. Explicitly not outliers.

## Stopping rule

**Fixed target: 48 runs.** If the run cannot complete — quota, an outage, anything — the
result is an **aborted study** and is reported as one, not analysed as a smaller
experiment. This replaces the stopping rule in the English terseness pre-registration,
which claimed quota exhaustion "cannot see the data"; it can, since quota is consumed by
the tokens the arms produce.

## What this run cannot settle

Six tasks is not "tasks in general", two languages is not "all languages", and the
delivery channel is a prompt prefix — not the skill body anyone installing this will
actually read. None of those are fixed here.
