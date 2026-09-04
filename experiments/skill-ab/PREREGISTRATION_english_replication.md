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
