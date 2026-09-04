# Pre-registration: does the terseness effect survive a change of language?

**Written and committed before any English run existed.** The commit that adds this file
adds no data; the data file it names does not yet exist. Check the git history if that
matters to you — it should.

## Why this run exists

Every A/B result in this repo was measured in Indonesian: the task prompts, the
one-sentence placebos, and the regex substance gates. The write-up is in English, and
until 2026-09-04 nothing in the repo said so. Round 21 of cross-family review made the
consequence explicit: the confirmatory run's headline — a one-sentence instruction cuts
output tokens ~23% against no instruction, 15 of 16 pairs, exact p = 0.0001 — is scored in
**output tokens**, and two languages do not tokenize alike. The number has no licence to
travel to the English sentence the skill file ships.

This run tests whether it travels.

## Hypothesis and prediction

**H1.** A one-sentence terseness instruction reduces total billed `output_tokens` when the
entire prompt surface is English, as it did in Indonesian.

**Registered prediction.** `oneline` uses fewer output tokens than `plain`, two-sided exact
paired permutation p < 0.05.

**What failure means, stated before the data exists.** If the prediction fails, the
terseness result is **language-bound**: it holds for the Indonesian strings that were
measured and does not generalise. The skill file must then say so and stop quoting the
figure next to an English sentence. There is no rescue round, no reanalysis on a second
endpoint, and no post-hoc subgroup.

## Design

- **Tasks:** the same four as the confirmatory run — `late_binding`, `set_order`,
  `shallow_copy`, `identity_cmp`. The fixture code is Python and unchanged; only the
  prompt language differs.
- **Arms:** two. `plain` (no instruction) and `oneline` (instruction prefixed to the
  prompt). The `mode` arm is **out of scope** — its Indonesian result was already null,
  and repeating a null in a second language answers nothing.
- **Repeats:** 4, giving **16 pairs** (4 tasks x 4 repeats), matching the confirmatory run.
- **Model:** `claude-haiku-4-5-20251001`, the same model as the confirmatory run.
- **Endpoint:** total billed `output_tokens` per run, summed over the run's turns, paired
  within (task, repeat).
- **Test:** exact paired permutation, two-sided, on the paired differences.
- **Substance gate:** the same `facts` regexes as the confirmatory run. They already accept
  both languages, so the same gate applies to both arms and both languages without
  translation — deliberately, so the gate cannot favour either.

## The strings

Indonesian (already measured, quoted for comparison):

```
prompt   : Jelaskan kenapa test_target.py gagal dan apa perbaikan yang benar.
           JANGAN menyunting berkas apa pun — cukup jawab.
oneliner : Jawab sesingkat mungkin, tanpa mengurangi isi teknisnya.
```

English (this run):

```
prompt   : Explain why test_target.py fails and what the correct fix is.
           Do NOT edit any file — just answer.
oneliner : Answer as briefly as possible, without reducing the technical content.
```

The English one-liner is a **faithful translation** of the Indonesian one, not the
looser phrasing the skill file shipped on 2026-09-03. That phrasing is being tested out of
the repo, not into it.

## Exclusions, fixed in advance

- A run with `rc != 0`, or with zero recorded turns, is dropped **together with its pair**.
- No other exclusion. In particular, no run is dropped for being an outlier.

## Stopping rule

The only reason this run may stop before 16 pairs is **exhausting the Claude subscription
quota**, which is a rule that cannot see the data. If it stops early, the achieved n is
reported as achieved, the test is run once on what completed, and the run is not repeated
later with a larger n — that would be optional stopping through the back door.

## What this run cannot settle

One additional language is not "all languages". A positive result licenses "the effect is
not specific to Indonesian"; it does not license "language does not matter". It also does
not test the **skill-body delivery channel** — the instruction is delivered here as a
prompt prefix, exactly as in the Indonesian run.

---

## Addendum, 2026-09-04, after the run — three defects in the protocol above

Written after the data existed and labelled as such. None of these change the registered
prediction or the analysis that was run; they record what the protocol got wrong.

**1. The stopping rule as written is false.** It says quota exhaustion "cannot see the
data". It can: quota is consumed by billed output tokens, which is the endpoint. A run
that stopped early for quota would have stopped *because* the arms were producing many
tokens. The rule should have been a fixed 32-run target with partial data declared an
aborted study, and that is how it will be written next time. It did not bite here — the
run completed all 32 with zero exclusions — but a rule that only works when it is not
needed is not a rule.

**2. The protocol registered no task-level analysis, and the task level is what
generalises.** Four tasks repeated four times is sixteen paired runs but four
observations of "a task". The run-level test answers "on these four fixtures, does the
sentence save tokens" and is valid for that. It does not license "on tasks in general".
A two-sided sign test across four tasks has a floor of 2/2^4 = 0.125 and cannot reach
0.05 whatever the data say, so the task level is reported as direction and magnitude
only, never as significance.

**3. The protocol registered no interaction test,** so comparing −22.7% with −19.6% by
reading two p-values side by side was never licensed. The interaction was computed after
the fact and is reported as post-hoc: mean difference-in-differences +3.5 pp,
exact p = 0.625 over four tasks. The claim that the English effect is *smaller* is
therefore withdrawn — the data do not support it.

A fourth item, raised by the same review and checked rather than conceded: the substance
gate scores 48/48 in every arm, which a reviewer called a gate that measures nothing. It
was given a negative control — empty, truncated and evasive answers, all four tasks — and
rejected every one, 0 of 3 facts in all twelve cases. The gate discriminates; the arms
simply all cleared it. `analyze_lang.py` runs that control on every invocation and
asserts on it.
