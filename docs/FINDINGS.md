# Findings

Basis: **1,316 Claude Code transcripts, 237,541 assistant turns, 741 overwrites** of
files the session had written itself (August 2026, one author, one model family).
Sessions of 50+ turns — the ones where any of this matters — are a 421-session cohort
of 233,549 turns, median length 484 turns.

The first edition of this repo used 24 transcripts and 122 overwrites. Two of its
three headline numbers did not survive the larger sample. Both corrections are below,
and the old numbers are named so they can be checked against.

Reproduce: `tools/extract.py` + `tools/simulate.py` for the overwrite analysis,
`tools/carry.py` for the carry table, `tools/skills.py` for the skill-listing audit.

## 1. Where the tokens actually go

**Units.** Every "byte" figure in this document is a character count from `len()`, not a
UTF-8 byte count. The two coincide for ASCII, the chars-to-tokens constant was calibrated on
the same count, and the shares are unaffected; only the label was wrong.

**Corpus version.** Both tables below come from the 421-session cohort, captured before the
section 10 run. Section 10 re-ran `tools/carry.py` over a later, larger corpus (1,080 files,
192,752 turns after the 50-turn filter) and got different shares — 45.11% where this table
says 42.53%. The two are not interchangeable: cite a share together with the cohort it came
from, not on its own.

Billed tokens over the 421-session cohort:

| bucket | tokens | share of volume | share of price* |
|---|---|---|---|
| cache_read | 81,931,794,477 | 97.44% | 68.8% |
| cache_creation | 1,874,911,161 | 2.23% | 19.7% |
| output | 273,406,545 | 0.33% | **11.5%** |
| input | 723,724 | 0.00% | 0.0% |

\* weighting cache-read 0.1x, cache-write 1.25x and output 5x the base input rate.
Volume share and price share are different questions and the difference is 35x on the
output row. An adversarial panel caught this repo asserting the volume number where
the price number belonged; see §7.

Anything entering the context at turn *i* is replayed on every turn after it, so its
cost is **carry = size x turns remaining** and total session input grows **O(N²)**.
Carry by source, same cohort:

| source | share of carry | bytes/turn |
|---|---|---|
| Bash call + result | **42.53%** | 656 |
| Read results | **21.28%** | 362 |
| Write + Edit calls | 9.51% | 155 |
| assistant prose | 5.63% | 91 |
| human prompts | 4.18% | 52 |
| injected attachments (all) | **15.32%** | 245 |
| — task reminders | 3.49% | 54 |
| — hook output | 3.26% + 2.79% | 93 |
| — skill/plugin listing | 3.22% | 43 |
| — nested memory files | 1.39% | 19 |
| other tools | 1.54% | 25 |

Three things fall out of this table.

**Tool results are the session.** Bash and Read together are 63.8% of carry. The
average Read result is 22.8 kB — 25x the average Bash result — off only 3,790 calls.
Reading a range instead of a file is the single largest per-call lever here.

**The scaffolding costs more than the speech.** Injected banners are 15.3% of carry
against assistant prose at 5.6%. The list of skills alone (median 22.8 kB, injected at
turn 0, so it is carried by every later turn) is worth 3.22% — more than half of all
prose. Uninstalling an unused plugin is a certain saving; being terser is a capped one.

**The skill listing is the largest single prunable item, and most of it is dead.**
`tools/skills.py` parses the listing out of the transcripts and counts every invocation
of every entry. On this setup, across 1,409 transcripts:

| | entries | bytes | share of listing |
|---|---|---|---|
| listing total | 82 | 30,009 | 100% |
| **never invoked once** | **66** | **21,891** | **72.9%** |
| — plugin A's skills | 21 | 6,781 | 22.6% |
| — plugin B's skills | 19 | 5,345 | 17.8% |
| — CLI built-ins | 14 | 6,174 | 20.6% |
| — the author's own skills | 10 | 3,358 | 11.2% |
| invoked at least once | 16 | 8,118 | 27.1% |

Total invocations behind that: 82 `Skill` tool calls and 572 slash invocations, spread
over 16 entries; the top one accounts for 157. The 21,891 never-invoked bytes are
**~6,972 tokens re-sent on every turn of every session** — ~3% of session carry, an
order of magnitude more than anything else this repo measures, and removable through a
supported setting rather than through better behaviour. Per the CLI's own settings
schema, `skillOverrides` is "keyed by skill name": `name-only` drops the description,
`user-invocable-only` hides the entry from the model but keeps `/name`, `off` hides it
from both. For a cold skill `user-invocable-only` recovers the whole entry and still
leaves it typeable — but a plugin may lock its skills, and a locked entry accepts only
`off` or `user-invocable-only`.

Cross-check: the CLI's `/skills` screen prints a live token cost per entry. Its figures
for one plugin's 20 skills summed to ~2,190 tokens against this tool's 6,781 bytes
(~2,159 tokens) — two independent instruments, 1.5% apart.

Claude Code ships the same question first-party: `/skill-doctor` reports "which loaded
skills are unused and costing context", `/skills` writes the `skillOverrides` setting,
and the CLI's own usage panel warns that skills "loaded but never invoked ... each one
adds to the system prompt every turn". Run those against this table — a number that two
independent instruments agree on is worth more than either alone. What this tool adds is
the archive: it counts every invocation ever made, not the live session's.

Two limits worth stating, the first of them serious. **"Never invoked" prices an entry;
it does not show the entry is inert.** The body never loaded, but the one-line
description sat in the model's context on every turn, and a description phrased as an
instruction ("use this before proposing a fix") can shape behaviour with no tool call at
all. An adversarial panel returned `PREMISE-BROKEN` on exactly this inference. The
measurement above survives that — the bytes are real and independently cross-priced — but
the conclusion "therefore free to remove" does not: removing a description is a behaviour
change of unknown sign. It may sharpen attention by shrinking an 82-item blob, or it may
delete a nudge that was working. Neither direction is measured here. The falsifying
experiment is behavioural, not accounting: take N tasks of the kind a skill claims to
serve, invoke it explicitly on half, and compare outcomes.
And both plugins whose skills score zero are genuinely in use — through `SessionStart`
hooks and MCP tools, not through the Skill tool — so the finding argues for pruning the
listing, not for uninstalling the plugin.

**Write is not where the fat is.** The first edition, measured on one long session,
put Write calls at 25.4% of carry and called them "2.5x over-represented". Across
1,316 sessions Write+Edit calls are **9.51%**. The old number was a single-session
artifact, and it is the reason this repo originally aimed its only rule at the wrong
target.

## 2. The overwrite decision: block count is the wrong feature

741 overwrites, of which 154 byte-identical (§3) and **587 real changes**.

The first edition reported 6.9 change blocks per overwrite and concluded that forcing
anchored edits costs +70%. On the full sample the mean is **2.6 blocks** (median 2),
and the conclusion inverts — but not in the direction the folklore expects either.

Applied to all 587, the rule this repo shipped — *"<=3 change blocks, use an Edit"* —
**loses 79-80% of the saving that was available**. Not "saves less than hoped": net
negative. Every threshold from `blocks<=1` to `blocks<=10`, with or without a minimum
file size, came out negative. The reason is mechanical: adjacent hunks merge, so a
single "block" can span most of a file, and the anchor context then costs more than
the rewrite it replaces.

The feature that works is the **changed fraction** f = (changed old tokens + changed
new tokens) / file tokens:

| f | n | Edit is cheaper | 95% CI | net tokens |
|---|---|---|---|---|
| <5% | 31 | 100.0% | 89-100% | +27,481 |
| 5-10% | 36 | 88.9% | 75-96% | +23,314 |
| 10-20% | 99 | 81.8% | 73-88% | +32,897 |
| 20-25% | 40 | 75.0% | 60-86% | +9,017 |
| 25-40% | 88 | 28.4% | 20-39% | −20,089 |
| 40-80% | 111 | 10.8% | 6-18% | −59,564 |
| >=80% | 182 | 0.0% | 0-2% | −163,731 |

Held out properly — tune the threshold on a random half of the **sessions**, score on
the other half, 20 splits — the tuned threshold lands at f = 0.25-0.29 (median 0.26)
and keeps **84.2% of the oracle saving** (worst split 75.4%, best 91.9%), negative in
**0 of 20** splits. The old block rule scores **−79.1%** on the same held-out halves.

Block count is not worthless — inside the 5-20% band, single-block rewrites are still
cheaper as Edits 100% of the time against 56-60% for 2-3 blocks — but it does not
survive as the primary feature.

**Two honest limits.** First, f is computed from the finished replacement, so it is a
*post-hoc* quantity: an agent applies it as an estimate ("am I changing under a quarter
of this file?"), not as a measurement. Second, the sample is 587 cases where the model
had already chosen to Write; edits it made instead are not in it.

Against the fear that anchored edits fail and the retry eats the saving: in this corpus
**Edit calls returned an error 6.19% of the time (821/13,272) and Write calls 12.17%
(618/5,080)**. Write's failures include workflow errors an Edit cannot have, so this is
not a clean like-for-like — but nothing here supports the claim that anchoring is the
riskier operation.

## 3. The part that holds: identical writes

**154 of 741 overwrites (20.8%) wrote content byte-identical to what was already on
disk.** The 24-transcript edition said 15% (18/122); the larger sample moved it up, not
down. Worth **0.077%** of carry — the same figure as the first edition, on 55x the data.

This is the only finding that survives every robustness cut (jackknife over 178
contributing sessions: 0.135-0.169%; bootstrap n=14: median 0.167%, range 0.112-0.221%;
holdout halves: 0.123-0.215%), and the only one that can be enforced mechanically.

It is *nearly*, not exactly, free. Suppressing the write costs a stat and a read, and
an identical write is occasionally deliberate — refreshing mtime, tripping a file
watcher, testing idempotency. `SAMEWRITE_ALLOW_NOOP=1` exists for that.

## 4. What an always-on instruction block costs

Any rule you install as a banner is itself context. A banner of **B** bytes injected at
turn 0 costs **B x N** of carry. A rule that removes fraction **f** of a source running
at **s** bytes/turn saves **f x s0 x N²/2**. So it pays for itself only after

    N* = 2B / (f x s0)        where s0 = s_observed / (1 - f)

Measured B, from the transcripts (median, sessions of 50+ turns, last 30 days):

| injected block | B |
|---|---|
| skill / plugin listing | 22,783 |
| hook additional context | 7,426 |
| a terse-output mode banner | 5,877 |
| a write-less-code mode banner | 5,298 |
| this repo's `edit-discipline` skill | 2,060 |

Measured s (bytes/turn, same cohort): prose 91, Write+Edit 155, Read 362, Bash 656.

f is the one term this corpus **cannot** supply. Both mode banners are `SessionStart`
hooks, so every session of 50+ turns has them on; the "off" group has a median length
of 1 turn and is made of aborted sessions. There is no control group here. Assuming
each skill's own claim for f, the formula gives:

| banner | target | f assumed | break-even |
|---|---|---|---|
| terse-output mode | prose | 0.65 | ~70 turns |
| write-less-code mode | Write+Edit | 0.30 | ~160 turns |
| `edit-discipline`, on its edit rule alone | Write+Edit | ~0.009 | **~2,700 turns** |

The last row is this repo indicting its own skill. The edit rule is worth 0.072% of
carry; the page carrying it costs 0.51% of a median session. **On the edit rule alone
the skill costs about seven times what it saves** — it only clears its own cost through
the second half of the page, the part that redirects attention to Bash and Read. A 2.5%
cut in Read carry pays for the whole page.

Two consequences worth stating plainly. Any always-on instruction block is a fixed tax
levied on long sessions and a dead loss on short ones. And a banner that only pays back
after ~160 turns pays back precisely in the sessions that should have been split in two.

**This section is a formula with measured B and s and an unmeasured f. It is not a
measured saving.** The measurement that would settle it is a hook-toggle A/B: run the
banner off for a randomised half of full-length sessions and compare bytes/turn.

## 5. External evidence

- Anthropic, *Effective context engineering for AI agents* — the framing this repo
  measures against.
- Augment Code, *AI Agent Loop Token Costs*: "context accumulation in naive agent loops
  follows a quadratic cost curve because the entire history is re-serialized and
  re-injected into the LLM's context window at every step". Independent statement of the
  O(N²) mechanism.
- Augment Code, *AI Coding Cost Analysis*: context editing (clearing stale tool results)
  reported at **84% token reduction in a 100-turn evaluation**; active context
  compression 57% on a SWE-bench task (4.0M → 1.7M). Stale tool results are 63.8% of
  carry here, so the two measurements point at the same place from opposite directions.
- arXiv 2605.26165, *Tool-Schema Compression*: "schema tokens scale linearly: JSON
  averages 380-473 tokens/tool ... yielding consistent 44.7-46.4% savings from 50 to 800
  tools". Direct support for the skill/tool-listing row of §1 — that cost is linear in
  how many tools you install and is prunable.
- aider's benchmark data (`aider/website/_data/*.yml`), same model in two formats:
  whole-file beats diff on pass rate in 4 of 6 pairs (well-formed 100% vs 71.6-92.5%,
  malformed 0 vs 68-148). Diff is not a free win — which is why §2's rule is a cost
  rule, not a correctness rule. aider has no no-op write guard; the gap in §3 is
  not covered upstream.

## 6. What this does not fix

Session length dominates everything measured here. Splitting a session in two cuts carry
to **46.5-59.3%** of the original on this data; into four, **23.8-39.1%**. Published work
on compaction reports −62.8…−85.9%.

Everything in this repo is worth ~0.1%. Session length is worth 50-88%. Do not mistake
one for the other.

**And it does not fix the language it was measured in.** Every A/B run below was conducted
in Indonesian — task prompts, one-sentence placebos, and the regex substance gates alike.
The two sentences that beat their own kilobyte blocks were, verbatim, `Jawab sesingkat
mungkin, tanpa mengurangi isi teknisnya.` and `Buat perubahan sekecil mungkin; jangan
menambah abstraksi yang tak diminta.` Every English phrasing in this document is a
translation that was never run. The exposure is uneven: the terseness contrast is scored in
output **tokens**, and two languages do not tokenize alike, so its magnitude has no licence
to travel; the line-count contrasts travel better. Twenty rounds of cross-family review did
not raise this, because no round read the rig — which is itself the finding: a panel
attacks what it is shown.

## 7. What an adversarial panel broke

Before publication these findings went to an 8-model, 4-family adversarial panel plus a
cross-family judge. Verdict: `PREMISE-OK`, confidence LOW, 8 of 12 claims grounded.
What it broke, and what was done about it:

- **"Output compression is capped at 5.6% of session cost" — broken.** 5.6% is a share
  of *carry*, and output tokens are billed at roughly 50x cache-read. Fixed: §1 now
  carries both a volume column and a price column, and the price column puts output at
  11.5%.
- **"Compaction invalidates carry" — tested, mostly refuted.** The objection: Claude Code
  compacts long sessions, so old tool results do not survive to turn 484 and carry
  overstates them. Test: compare actual billed input per turn against the cumulative
  transcript size at the 90th-percentile turn of every 200+-turn session (n=349). Median
  ratio **2.43** (p10 0.73, p90 2.99) — actual context is consistently *larger* than the
  transcript predicts, because the system prompt and tool schemas are not in the
  transcript. Only **11%** of long sessions show the sharp drop compaction would produce.
  Carry is not systematically inflated. It is also not a measurement of every session.
- **"The f threshold is tuned and scored on the same 587 cases" — valid, fixed.** §2 now
  reports session-level held-out validation across 20 splits.
- **"f is oracle leakage" — valid, not fixable.** Stated as a limit in §2 instead.
- **"Zero trade-off is false" — valid, fixed.** §3 no longer claims zero.
- **"C4's arithmetic is off by ~12%" — valid, fixed.** §4 now derives s0 from the
  observed post-rule rate explicitly rather than substituting the observed rate for the
  counterfactual one.
- **"f is unmeasurable" — wrong, and this repo was wrong to say it.** Unmeasured in this
  corpus is not unmeasurable: a hook-toggle A/B measures it. §4 says so and names it as
  the outstanding experiment.
- **The panel's own blind spot**, in the judge's words: five of five advisors converged on
  "carry ≠ dollar cost" from shared prior, not evidence, and replaced measured-but-
  confounded numbers with plausible-but-unmeasured ones ("retry loops dominate" is as
  unmeasured as anything it attacked — §2 now measures it: 6.19% vs 12.17%). On a flat
  subscription, where quota and context pressure are the binding constraints rather than
  dollars, carry is the right metric and the panel's headline attack does not land.

## 9. What an always-on skill costs, measured twice

§4 gives a formula for what an instruction block costs. This section measures one, end to
end, on a task the skill explicitly claims: `systematic-debugging` ("ALWAYS find root cause
before attempting fixes. Symptom fixes are failure").

**Design.** Bug fixtures where the symptom differs from the root cause. A symptom-only fix
turns the TARGET test green while a NEIGHBOR test — never present in the working directory
while the agent runs — stays red. Scoring is mechanical, no LLM judge: `FAIL` (target red),
`SYMPTOM` (target green, neighbor red), `ROOT` (both green), `INVALID` (agent edited a test).
Before any agent ran, a known-good "golden fix" was applied to every fixture to prove `ROOT`
is reachable. Two arms differ by one sentence: the second prompt says to invoke the skill
first. **Treatment verified, not assumed** — every skill-arm run's transcript contains a
`Skill` tool call loading `systematic-debugging` (36/36), and no plain-arm run does (0/36).

| | round 1 | round 2 |
|---|---|---|
| fixtures | 6 single-file | 6 multi-file, misleading locus |
| runs scored | 36 | 36 |
| config | host's real config (~45 kB preamble + hooks) | minimal config, only the skill |
| plain arm | 18 ROOT | 17 ROOT, 1 FAIL |
| skill arm | 18 ROOT | 16 ROOT, 2 FAIL |
| tokens/task, plain | 402,108 | 389,747 |
| tokens/task, skill | 723,309 | 653,168 |
| delta | **+79.9%** | **+67.6%** |
| paired, skill costlier | 17 of 18 | **18 of 18** |
| sign test (two-sided, no ties) | p ≈ 0.00015 | p ≈ 0.00001 |

Token figures are **per run**, not arm totals (round-1 plain ranged 212,992–560,391 across
its 18 runs).

**The cost replicates; the benefit was never measurable.** Across both rounds the plain arm
reached `ROOT` in 35 of 36 runs. Only one fixture ever produced a disagreement, and it
disagreed in both directions (plain failed once, the skill arm failed twice) — a coin flip,
not an effect. So this is a **ceiling**, and a ceiling identifies nothing: it does not show
the skill is useless, it shows these fixtures had no room for it to help. Two attempts to
build headroom failed, and the second set was designed *after* seeing the first ceiling by
the same author — they are two attempts, not two independent replications.

### Round 3: building headroom on purpose

Rounds 1 and 2 could not measure the benefit because the control arm never failed. Round 3
attacked that directly, from one observation: **the agent stops the moment the target test
goes green.** So a fixture only has headroom when a *local* patch near the symptom is enough
to turn the target green while the real cause sits several hops away, in a module the
symptom's file does not import. The neighbour test separates them.

Two mechanical controls ran before any agent did, and both are cheap:

- **positive** — apply the root fix: target green *and* neighbour green (proves `ROOT` is
  reachable);
- **negative** — apply the shortcut patch: target green *and* neighbour **red** (proves the
  trap exists).

The negative control earned its place immediately: it disqualified a sorting fixture whose
"shortcut" (sorting the rendered `"dept:name"` strings) turns out to be equivalent to the
root fix, because the department is the string prefix. That fixture could not have
discriminated anything, and without the negative control it would have shipped.

The protocol was written down before any run
([PREREGISTRATION](../experiments/skill-ab/PREREGISTRATION_round3.md)): pilot the control
arm only, admit a fixture to the A/B if the control failed at least once in 3 repeats —
selection on the **control arm alone**, never on the plain-vs-skill difference — and if
nothing qualifies, report a third failure rather than tune the fixtures further.

Pilot, 5 frozen fixtures x 3 control runs: four still at ceiling (3/3 `ROOT`), and one,
`scale_table`, at `SYMPTOM` 3/3. One qualifier. Repeats were raised 3 -> 6 for power, a
deviation declared in the pre-registration before any skill-arm run existed.

**The A/B on the one fixture with headroom, 6 pairs, treatment verified 6/6 and 0/6:**

| | reached root cause | took the shortcut | tokens/task |
|---|---|---|---|
| without the skill | **2 of 6** | 4 of 6 | 464,030 |
| with the skill | **0 of 6** | 6 of 6 | 775,510 (**+67.1%**) |

McNemar on the 2 discordant pairs: both favour the control, two-sided p = 0.50 — **not
significant**, and 2 discordant pairs cannot be. The cost difference is: costlier in 6 of 6
pairs, two-sided sign test p = 0.031.

So the honest summary of three rounds is not "the skill does nothing". It is narrower and
more useful: **the first time a fixture left room to find a root cause, the arm instructed
to find root causes did not find one, and paid 67% more to not find it.** One fixture, one
model, six pairs. That is a signal worth a bigger experiment, not a verdict.

### Round 4: a generator hypothesis, falsified — and the first sign the skill does something

Round 3 left one fixture with headroom and four at the ceiling. The difference looked
structural, so it was written as a generator and **pre-registered with a kill condition**:
the defect has N *sibling instances* in a homogeneous collection, the target test names
exactly one, the neighbour tests the siblings. Prediction: all five new fixtures (five
different substrates — data-table rows, mis-parsed config values, a shared helper missing a
guard across four call sites, a base-class defect inherited by four subclasses, a
copy-pasted bug in 3 of 12 registry handlers) would show headroom; **if two or more came
back at the ceiling, the hypothesis was wrong and would be published as wrong.**

Control-arm pilot, 3 runs each: `scale_table`, `handler_registry`, `sibling_callers` all at
`SYMPTOM` 3/3 — and `config_keys` and `subclass_family` at `ROOT` 3/3. **Two of five. The
kill condition fired.** Sibling structure is necessary but not sufficient.

**Before trusting any of it, the oracle was audited.** An adversarial panel's sharpest point
was that the hidden neighbour test is escapable — an agent could hard-code the three tested
values and satisfy both tests without repairing anything, which would mean earlier `ROOT`
verdicts were oracle weakness rather than control strength. That is checkable without
running anything: for every `ROOT` verdict, did the file containing the root cause actually
change? **28 of 28 did. Zero escapes.** The ceiling in rounds 1–3 was real.

The A/B on the three qualifying fixtures, 4 repeats each, treatment verified 12/12 and 0/12:

| fixture | root fix lives in | control reached root | skill arm reached root |
|---|---|---|---|
| `handler_registry` | 3 of 12 copy-pasted functions | 0 of 4 | 0 of 4 |
| `scale_table` | 3 rows of a 40-row data table | 1 of 4 | 0 of 4 |
| `sibling_callers` | **one shared helper** | **0 of 4** | **4 of 4** |

Pooled McNemar — the pre-registered primary — is 5 discordant pairs, 1 favouring control and
4 favouring the skill: **p = 0.375, not significant.** It is also exactly the sign split the
panel warned pooling would hide, which is why the per-fixture rows above matter more than the
pooled number.

On `sibling_callers` the separation is complete and the mechanism is visible in the diffs.
The control arm put the guard in `routes/posts.py` — the one call site the failing test names
— leaving three sibling callers broken. The skill arm put it in `util/text.py`, the shared
helper, fixing all four. That is precisely what the skill claims to do, and the first time in
four rounds it did it.

**What this is and is not.** It is hypothesis-generating: one fixture, four pairs, p = 0.125
on its own discordant cells, from a design whose pre-registered primary analysis came back
non-significant. It is not a demonstration that the skill works. The reading it supports is
narrower and testable: the skill may help when repairing the class means choosing **one
shared code site** over the named call site, and did nothing at all when repairing the class
meant editing N data rows or N duplicated functions — where there is no single root to find.

Cost, meanwhile, replicated a fourth time: **+51.1% tokens, costlier in 12 of 12 pairs,
two-sided sign test p = 0.0005.** Across four rounds: +79.9%, +67.6%, +67.1%, +51.1%.

### Round 5: a second hypothesis falsified, and a placebo that changes the question

Round 4's one positive signal came from a fixture whose root fix lived in a single shared
helper. Round 5 pre-registered that as the class and tested six of them — a helper missing a
guard (negative limit, leading slash, missing dict key, zero denominator, trailing separator,
tab whitespace), each with four or more callers in separate files, target test naming one
caller. Prediction, written first: **at least 4 of 6 show headroom; if fewer, the claim is
wrong.**

Result: **1 of 6.** `truncate_guard` trapped the control 3/3; the other five were repaired at
the helper 3/3. The threshold fired again. Two pre-registered generator hypotheses, two
falsifications, both by conditions written before the data existed.

**The methodological lesson is the more useful half.** Every one of those five fixtures had a
valid shortcut — the mechanical negative control proved it, because I wrote the shortcut
myself and watched it turn the target green and the neighbour red. The agent simply never
took it. So the negative control proves a shortcut **exists**, not that it is **attractive**,
and only a control-arm pilot measures attractiveness. In the five that failed to trap, the
caller was a pure pass-through with nothing local to guard; in `truncate_guard` the caller
owned its own `n` parameter, so guarding it there felt natural. That is a hypothesis for a
later round, not a finding here.

**A third oracle and a third arm.** ROOT now also requires a **holdout caller** — a new
consumer of the helper written only *after* the agent's patch lands, which a call-site repair
cannot satisfy and the agent cannot anticipate. And a **placebo arm** was added: a
length-matched prompt urging care, planning and re-checking, with no mention of root causes,
because the strongest non-causal story for rounds 1–4 was budget rather than reasoning.

On the single fixture with headroom, 4 pairs per arm, treatment verified 4/4 and 0/8:

| arm | reached root cause | took the shortcut | tokens/task |
|---|---|---|---|
| plain | **1 of 4** | 3 of 4 | 424,557 |
| placebo (care + planning) | 0 of 4 | 4 of 4 | 478,447 (+12.7%) |
| skill | 0 of 4 | 4 of 4 | **780,209 (+83.8%)** |

`placebo` and `skill` produced **zero discordant pairs** — identical outcomes. The
pre-registered gate said a skill effect counts only if it beats the placebo; it did not.
What it did do is cost **+63.1% more tokens than the one-sentence deliberation prompt for the
same result** (costlier in 4 of 4 pairs). Four pairs prove nothing on their own; the direction
is what is worth carrying forward.

**What an adversarial panel broke in this design, and what stands.** Two proposed escapes
from the holdout oracle were killed on inspection — an agent cannot guard a file that does
not exist yet, and the call-site repair does fail the holdout, exactly as the shortcut control
shows. Three objections stand and are recorded as limits: the holdout **leaks in both
directions** (a helper-level patch that hard-codes the tested values would satisfy it; a
legitimate class repair with a different contract could fail it); the **placebo is not inert**
— urging care is itself a treatment, so this compares two treatments rather than treatment
against nothing; and prompt-matching does **not** bound the budget confound, which needs hard
caps on tokens, tool calls and retries. The estimand is six fixed, correlated, single-author
fixtures — not a population of bugs.

Provenance audit, unchanged in method and extended: **44 of 44** `ROOT` verdicts across all
rounds touched the file containing the root cause. Still zero escapes.

### Round 6: the third hypothesis holds — and one sentence beats the skill

Round 5's post-hoc guess was that headroom needs a caller with **something of its own worth
guarding**, since the five fixtures that failed to trap had pure pass-through callers. Round 6
pre-registered that, with six different reasons a local guard would feel natural: a
caller-owned default; a caller-owned page size; an argument the caller **computes**; a caller
that already has one pre-check; a caller that already has a `try/except`; a mode flag the
caller holds. Prediction: at least 4 of 6 show headroom.

**4 of 6.** The first pre-registered prediction in this program to survive. (`mode_flag` and
`page_size` were repaired at the helper 3/3; two of the qualifiers landed in the informative
33–67% band rather than at the floor.)

An adversarial panel then downgraded the round before the A/B finished, and it was right to:
"natural to guard locally" can collapse into "the model took the shortcut", which is the
outcome defining its own cause unless the feature is frozen as a machine-checkable predicate.
The fixtures were labelled by structural reasons written before any run, but never formalised
that way — so **round 6 is recorded as a final frozen exploratory test, not a confirmatory
one, and there is no seventh generator.**

The A/B, 4 fixtures x 3 arms x 4 repeats, 48 runs, treatment verified 16/16 and 0/32:

| fixture | plain | placebo | skill |
|---|---|---|---|
| `caller_computes` | 4/4 | 4/4 | 3/4 |
| `caller_try` | 0/4 | 0/4 | 0/4 |
| `existing_precheck` | 0/4 | **3/4** | 1/4 |
| `truncate_guard` | 1/4 | 0/4 | 1/4 |

| contrast | discordant pairs | direction | p (two-sided) |
|---|---|---|---|
| plain vs skill | 2 | 1 / 1 | 1.00 |
| **placebo vs skill** | 4 | **placebo 3, skill 1** | 0.625 |
| plain vs placebo | 4 | placebo 3 | 0.625 |

| arm | tokens/task | vs plain | vs placebo |
|---|---|---|---|
| plain | 428,329 | — | — |
| placebo (one sentence: work carefully, plan, re-check) | 477,414 | +11.5% | — |
| skill (9.4 kB, invoked and verified) | **743,283** | **+73.5%** | **+55.7%** |

Costlier in **16 of 16** paired runs against both arms, two-sided sign test p < 0.0001.

**The result that survives six rounds is this: the skill never beat the placebo.** In round 6
the one-sentence prompt was directionally *ahead* of it — 3 discordant pairs to 1 — and on
`existing_precheck` the placebo reached the root cause 3 times out of 4 where the control
managed 0 and the skill 1. None of those contrasts is significant (p = 0.625, four discordant
pairs), and they are not offered as one. The claim is narrower and it is about cost: **a
sentence did the same work as 9.4 kB of process, for 56% fewer tokens.**

Provenance audit across all six rounds: **62 of 62** `ROOT` verdicts touched the file holding
the root cause. Zero escapes.

**What is still wrong with this, in the panel's words and mine.** Per-round pre-registration
protects each round, not the sequence — this was the third generator on one harness, and the
per-round p-values carry no family-wise correction. The placebo matched the skill's *length*,
not its *interaction shape*: the skill mandates a phased workflow, so "skill vs placebo" still
mixes the skill's content with the fact that it imposes a procedure. Six surface-different
fixtures may be isomorphic to the harness, so the effective N is below six. And one model,
one author, tiny Python packages — the estimand is this benchmark, not debugging.

### Round 7: the two skills that are actually always on — and a unit error that flipped a result

Six rounds tested a skill that was **never invoked once** in 1,409 transcripts. Two others are
injected into *every* session by `SessionStart` hooks and pay carry on every turn: a terse-output
mode (4,664 bytes, claiming "−65% output tokens, all technical substance stays") and a
lazy-engineer mode (5,228 bytes, claiming "shortest working diff, no unrequested abstractions").
Round 7 puts those two through the same rig, with the real banners extracted from live
transcripts and injected through the same hook mechanism production uses — so the treatment is
verifiable in the transcript rather than assumed. It was: banner present in 12/12 of the mode
arm's runs and 0/12 everywhere else, in both experiments.

**The unit error, and why it matters.** The first pass scored the terse mode by *word count*,
because that is easy and mechanical. An adversarial panel's first objection was that the claim
is about **tokens**, and words are not tokens — dropped articles, fragments and verbatim code
tokenize differently. Rescoring the same 36 runs on billed `output_tokens` changed the answer:

| contrast | by word count | by output tokens |
|---|---|---|
| one-sentence placebo vs plain | −37.3%, 12/12, p = 0.0005 | −14.5%, 11/12, p = 0.0063 |
| full banner vs plain | −35.8%, 12/12, p = 0.0005 | **−22.4%**, 11/12, p = 0.0063 |
| **full banner vs the one-sentence placebo** | +2.3%, 5/12, **p = 0.77** | **−9.2%, 10/12, p = 0.039** |

By words the banner and the sentence were indistinguishable. By tokens the banner is genuinely
ahead. **This is the first time in seven rounds that a full skill beat a one-sentence placebo
on a significance test** — and it only appeared once the metric matched the claim.

**Does it pay for itself?** The banner costs input on every turn and saves output once. Per task
on this benchmark: **+2,337 input tokens, −634 output tokens.** Priced at published rates, that
is net positive at every tier, because output is 5x input:

| model | output saved | banner input cost | net, per 1,000 tasks |
|---|---|---|---|
| Fable 5 | $31.69 | $2.34 | **+$29.35** |
| Opus 5 | $15.84 | $1.17 | **+$14.68** |
| Sonnet 5 | $6.34 | $0.47 | **+$5.87** |
| Haiku 4.5 | $3.17 | $0.23 | **+$2.94** |

**But the claim is still about three times its measured size.** The pre-registered prediction was
a reduction of at least 50%, since the banner claims 65%. Measured: 22.4%. That prediction failed
and is written up as failed. A substance gate ran alongside — a fixed regex list of facts each
answer had to contain — and it dropped from 100% (plain) to 97% in both compressed arms: a small
but non-zero cost for the compression. The gate is mine and it is weak; a terse answer can satisfy
all three patterns while stating the relation backwards.

**The lazy-engineer mode produced no signal, and the reason is a ceiling, not a verdict.** Four
implement-tasks that invite over-engineering, all three arms 12/12 green: added lines 2.33 (plain),
2.50 (one-liner), 2.17 (banner), and **zero** new classes, functions or files in any arm. Nobody
over-engineered, so there was nothing to prevent. Pre-registered prediction — the banner beats
plain on 3 of 4 fixtures — came back 1 of 4 and is written up as failed. On tasks this small the
experiment cannot measure the claim; that is a fixture problem, exactly like rounds 1–3.

### Round 8: bigger tasks for the lazy-engineer mode — and one sentence wins again

Round 7's lazy-engineer result was a ceiling: four 3-line tasks, nothing to over-engineer.
Round 8 replaced them with four tasks where over-building is genuinely common — parse and
group-sum a CSV, a sliding-window rate limiter, retry with exponential backoff and give-up, a
decorator-based plugin registry with dispatch. Minimal solutions are 8–15 lines; the obvious
over-built versions bring classes, strategy objects and dataclasses. Tests pin behaviour only.

36 runs, every arm 12/12 green:

| metric | plain | one-sentence placebo | full banner (5,228 B) |
|---|---|---|---|
| non-blank lines | 10.33 | **9.42** | 9.92 |
| new defs/classes | 1.50 | 1.50 | 1.50 |
| new imports | 0.25 | 0.25 | 0.25 |
| new files | 0.08 | 0.08 | 0.00 |

| contrast | pairs | result |
|---|---|---|
| one-sentence vs plain | 7 | fewer lines **7 of 7**, p = 0.016 |
| banner vs plain | 7 | 5 of 7, p = 0.45 |
| banner vs one-sentence | 6 | 2 of 6, p = 0.69 |

The pre-registered prediction — the banner beats plain on 3 of 4 fixtures — came back **2 of 4
and is written up as failed.** A single sentence ("make the smallest possible change, add no
unrequested abstraction") produced a significant reduction; 5,228 bytes of rules did not, and
did not beat the sentence. Identical def and import counts across all three arms say the
remaining headroom is still small: nobody over-engineered these either.

### Does the terse mode still pay in a long session? (the panel's best objection, tested)

An adversarial panel's sharpest point about round 7 was not about the statistics: a
`SessionStart` banner rides in the context of **every turn**, while the output saving is
counted once. If real sessions are long, the one positive result in this whole program could
flip sign. That is checkable with the runs already recorded.

The runs were not short. Median **9 turns** (mean 9.2, max 14), so the measured input delta of
**+2,337 tokens already contains nine turns of banner replay** — about **255 billed input
tokens per turn**, far under the 4,664 bytes ≈ 1,485 tokens a naive reading suggests, because
what is billed after the first turn is cache-read.

A second panel then rejected that reading, correctly: **255 reconciles with nothing** — not
full price (the banner is ~1,485 tokens) and not a clean cache-read of it either. The number
mixed a token count with a billing weight. Its recommended fix cost no new runs — decompose the
per-turn billing fields already recorded — so that is what was done.

**Decomposition, mode minus plain, averaged over 12 runs per arm:**

| field | delta | reading |
|---|---|---|
| `input_tokens` | **−5** | the banner is **not** billed at full rate — if the cache missed this would be ≈ +1,485 |
| `cache_creation_input_tokens` | −4,628 | the mode arm *writes less* cache |
| `cache_read_input_tokens` | **+6,970** | ≈ **+760 per turn**, the banner's real recurring cost |
| `output_tokens` | −634 | ≈ −69 per turn |

The mechanism is confirmed: the banner is served from cache, not re-billed. The per-turn
figure needed fixing **twice**, and the second fix matters. Dividing a total delta by one arm's
turn count (6,970 / 9.2 = 758) silently compares arms that ran different numbers of turns.
The defensible form is rate against rate:

| per turn | plain | mode | delta | at published rates |
|---|---|---|---|---|
| `cache_read` | 19,566 | 21,174 | **+1,608** | +161 units |
| `cache_creation` | 2,750 | 2,367 | −383 | −479 units |
| `output` | 295 | 239 | **−56** | −280 units |

**Net ≈ −598 units per turn — a saving.** Ignore the cache-write term entirely and it is still
−119. So the conclusion survives the stricter comparison, but three different per-turn numbers
came out of the same data (255, 760, 1,608) purely from how the denominator was chosen. Every
one of the first two was wrong, and both were caught by review rather than by me. Treat any
per-turn figure in this document as a rate-vs-rate comparison or not at all.

The panel's fatal case required the banner to be re-billed at full input rate on most turns;
the `input_tokens` delta of −5 says it was not.

Two things this still does not explain. The mode arm **writes less cache** (−383/turn), which
is plausible — terser output means less new context to cache — but it is inferred, not shown.
And it used **0.4 fewer turns** (9.6 → 9.2), so about 3 of the 22 percentage points of output
saving come from ending sooner rather than from being terser; the remaining 19 points are a
genuine per-turn compression.

**And the savings do not saturate — they grow.** Output delta by turn index (mode minus plain):

| turn | 0–1 | 2–3 | 4–5 | 6–7 | 8 | 9+ |
|---|---|---|---|---|---|---|
| delta | +22 | −72, −39 | +51, +27 | −165, −130 | −70 | −167 |

Early turns are a wash; the compression bites hardest late, where a verbose model pads
summaries and wrap-ups after tool results. That is the opposite of the "savings saturate"
prediction, and it was the judge's own steelman rather than mine.

The objection was still worth raising, and one framing of it is genuinely fatal: if you hold
the output saving fixed while letting the banner replay grow, break-even lands near 124 turns.
That model only applies if the assistant stops producing prose after the first task, which is
not what a session looks like. Stated correctly, the terse mode's return does not depend on
session length — but it does depend on the 5:1 output-to-input price ratio and on cache-read
actually being hit, and both are assumptions rather than measurements here.

### The terse-mode result does not survive an equal-length comparison — retraction

The last panel's one supported premise was that a per-turn scalar over runs of unequal length
is not a valid comparison. Following that through with the data already recorded overturns this
program's only positive result.

Compare the two arms over the **same number of turns**, pairs restricted to runs that reach
that horizon:

| horizon | pairs | plain output | mode output | delta | mode shorter | p |
|---|---|---|---|---|---|---|
| 5 turns | 12 | 896 | 879 | −1.9% | 5/12 | 0.77 |
| 6 turns | 12 | 1,118 | 1,127 | **+0.9%** | 5/12 | 0.77 |
| 7 turns | 10 | 1,646 | 1,351 | −17.9% | 5/10 | 1.00 |
| 8 turns | 8 | 2,120 | 1,499 | −29.3% | 6/8 | 0.29 |
| 9 turns | 4 | 1,804 | 1,808 | +0.2% | 2/4 | 1.00 |
| **full run, unequal lengths** | 12 | 2,830 | 2,196 | **−22.4%** | **11/12** | **0.0063** |

The headline −22.4% at p = 0.0063 exists **only in the last row** — the one that sums over runs
of different lengths. On every equal-length horizon the paired sign count falls to roughly a
coin flip. At the horizon every pair reaches (6 turns), the difference is **+0.9%: no
compression at all.**

**That mechanism was wrong, and the retraction went too far.** The next thing to check was
whether turn counts actually differ. No directional difference is detectable: paired differences
run from −6 to +6, mean −0.42, mode shorter in 6 of 11 non-tied pairs, **two-sided p = 1.000**.
That is absence of evidence for a difference, **not evidence of equivalence** — it does not
exclude informative stopping or a difference in trajectory composition, and a later panel was
right to say so. There is no
turn-count difference to credit the mode arm for. In several pairs the mode arm took *more*
turns and still produced less total output, which strengthens the effect rather than explaining
it away.

So the correct reading is narrower than either the original claim or the retraction. The
total-run effect — −22.4%, 11 of 12 pairs, p = 0.0063 — **stands, and is not a turn-count
artifact.** What fails is the description of it as a uniform per-turn compression: through turn
6 there is none (+0.9%, 5/12), and the point estimates only turn large at k = 7 and k = 8
(−17.9%, −29.3%) where the pair count drops to 10 and 8 and significance is lost to sample
size, not to absence of effect. **Truncating at six turns tests precisely the region where the
effect does not live**, so it is not a refutation of a late-onset effect.

**What is withdrawn**, then, is the mechanism and the framing, not the measurement: what the data supports is a **late-onset total-run
reduction** of 22.4% (11/12, p = 0.0063) whose per-turn profile is flat early and steep late,
measured on four explain-only tasks with 12 pairs, where the long-horizon cells are too small
(8 and 4 pairs) to pin the onset point. The `input_tokens`
delta of −5 still shows the banner is served from cache rather than re-billed, and the
cache-write reduction is still unexplained; neither rescues an output saving that is not there.

**And the process point, which is the durable part.** Four numbers in this analysis were wrong
before this one: 255, then 760, then 1,608 tokens per turn, then a −22.4% saving that was a
turn-count artifact. Three were caught by adversarial review and the fourth by following
review's advice further than review did. A single-arm summary statistic over variable-length
sessions is the trap; the fix is to fix the horizon before comparing anything.

### The confirmatory run: the banner adds nothing over one sentence

Everything above is exploratory. This is the run that was pre-registered before the data
existed, on **four tasks never used before**, with one endpoint, one test, and exclusion rules
fixed in advance: paired total billed `output_tokens`, contrast **mode versus the one-sentence
placebo**, exact paired permutation test, two-sided. The prediction on record was that the
banner would win at p < 0.05, and that failing to win would mean the benefit is **not
replicated, with no rescue round**.

48 runs, **zero exclusions** — no run errored, and treatment verification was perfect: the
banner appeared in all 16 mode runs and none of the other 32.

| contrast | pairs | tokens | delta | mode lower in | exact p |
|---|---|---|---|---|---|
| **mode vs one-sentence placebo** (primary) | 16 | 2,388 → 2,369 | **−0.8%** | 6/16 | **0.855** |
| mode vs plain (secondary) | 16 | 3,091 → 2,369 | **−23.4%** | **15/16** | **0.0001** |

Substance gate: **100% of required facts in all three arms.**

**The pre-registered prediction failed, and that is the finding.** The earlier −9.2% at
p = 0.039 does not replicate; on fresh tasks the 4,664-byte banner and a single sentence are
indistinguishable (−0.8%, p = 0.86). What *does* replicate, and hard, is terseness itself:
either instruction cuts output by roughly a quarter against no instruction, 15 of 16 pairs,
p = 0.0001 — closely matching the −22.4% measured on the earlier task set.

Per task the two treated arms track each other everywhere:

| task | plain | one sentence | banner |
|---|---|---|---|
| `identity_cmp` | 2,958 | 2,195 | 2,405 |
| `late_binding` | 3,460 | 2,504 | 2,473 |
| `set_order` | 3,148 | 2,899 | 2,652 |
| `shallow_copy` | 2,798 | 1,955 | 1,947 |

**So the eight-round arc closes here.** Three always-on instruction blocks were tested against
one-sentence versions of their own intent. None of them beat the sentence on a pre-registered
test. The instruction is worth having; the kilobytes are not.

### The English replication: the sentence travels, the magnitude shrinks a little

Round 21 of adversarial review noticed what twenty rounds before it had not: every run
above was conducted in Indonesian, and the numbers were being quoted beside English
sentences. The endpoint is `output_tokens`, and two languages do not tokenize alike, so
the objection had teeth. The protocol was pre-registered at commit `2a6edd3`, before the
data file existed — the prediction on record was that the one-sentence instruction would
still beat no instruction at p < 0.05, and that failure would mean the effect is
language-bound with no rescue round.

Same four tasks, same model, same substance gates, 16 pairs, prompt prefix delivery:

| language | plain | one sentence | delta | sentence lower in | exact p |
|---|---|---|---|---|---|
| Indonesian | 3,091 | 2,388 | **−22.7%** | 14/16 | **0.0001** |
| English | 2,870 | 2,308 | **−19.6%** | 12/16 | **0.0070** |

**The prediction held, and the honest form of it is directional.** The sentence used
fewer output tokens in **4 of 4 tasks in both languages**, which is the part that
replicates. The magnitudes are not comparable by reading two p-values side by side, and a
post-hoc interaction test on the task-level deltas says so: mean difference-in-differences
**+3.5 pp, exact p = 0.625** over four tasks. **The claim that the English effect is
smaller is withdrawn** — the data do not support it.

**Four tasks is four observations, whatever the repeat count.** The run-level test above
is valid for the question "on these four fixtures, does the sentence save tokens". It does
not license "on tasks in general": a two-sided sign test across four tasks has a floor of
2/2⁴ = **0.125** and could not reach 0.05 however clean the result. Per task, one sentence
against none:

| task | Indonesian | English |
|---|---|---|
| `identity_cmp` | −25.8% | −10.3% |
| `late_binding` | −27.6% | −25.6% |
| `set_order` | −7.9% | −20.5% |
| `shallow_copy` | −30.1% | −21.1% |

The substance gate stayed at **48/48 in every arm of both languages**. A reviewer's
objection was that a gate which never fails has not been shown to measure anything, so it
was given a negative control: empty, truncated and evasive answers, all four tasks. It
rejected every one — 0 of 3 facts in all twelve cases. `analyze_lang.py` reruns that
control on each invocation and asserts on it, so the gate cannot rot into a rubber stamp
unnoticed.

**What this fixes in the write-up, beyond the language.** Recomputing all three contrasts
with one script exposed a second misattribution, this one nothing to do with translation:
the **−23.4%, 15 of 16** figure quoted throughout as "telling the model to be terse" is
the *banner* arm against plain. The *sentence* against plain is **−22.7%, 14 of 16**. The
two are within a point of each other — which is the whole point of section 9 — but they
are different arms and had been used interchangeably.

| contrast (Indonesian, n = 16) | mean plain → treated | delta | lower in | exact p |
|---|---|---|---|---|
| one sentence vs plain | 3,091 → 2,388 | −22.7% | 14/16 | 0.0001 |
| banner vs plain | 3,091 → 2,369 | −23.4% | 15/16 | 0.0001 |
| banner vs one sentence | 2,388 → 2,369 | −0.8% | 6/16 | 0.855 |

**Two languages is not all languages,** and the minimal-change result still has only one:
it was never re-run in English, its n is 7, and its endpoint is lines rather than tokens.
That asymmetry is now stated in the skill file rather than smoothed over.

### The minimal-change replication: a pre-registered null, and a design that could not have won

The terseness result replicated. The minimal-change result was put through the same
treatment and did not, and the protocol said in advance what that would mean.

Two gaps drove it. The 7-of-7, p = 0.016 figure quoted throughout comes from
`runs/exploratory/ab8.jsonl`, which the manifest has always classified **exploratory,
not pre-registered** — and the skill file had been printing it beside a confirmatory
result without distinguishing them. And four fixtures cannot carry a significance claim
however many repeats they get. So the protocol
([PREREGISTRATION_minimal_change_english.md](../experiments/skill-ab/PREREGISTRATION_minimal_change_english.md),
committed at `0436efe` before the data existed) used **six** tasks — two written for this
run and given a hand-written minimal solution plus a green `pytest` as a positive control
first — and registered the task-level sign test as primary.

48 runs, **zero failed the correctness gate, zero pairs dropped**:

| | smaller in | tied | total lines | sign test | floor |
|---|---|---|---|---|---|
| **English (primary)** | 5/6 | 1 | 132 → 116 (−12.1%) | **p = 0.0625** | 0.0625 |
| Indonesian | 4/6 | 2 | 126 → 117 (−7.1%) | p = 0.1250 | 0.1250 |

**The registered prediction failed.** Per the protocol: the minimal-change result does not
replicate as confirmatory evidence at this task count, the exploratory 7-of-7 stands as
exploratory only, and there is no rescue round.

**The design lost its ability to reject the moment one task tied — a hazard the
pre-registration missed.** Six tasks were chosen precisely so the sign-test floor would be
2/2⁶ = 0.031, below 0.05. With zero ties that design could have rejected; a sign test
discards ties, though, and the endpoint — non-blank lines, ranging 8 to 27 — is coarse
enough that ties happen. One tie drops the denominator to five and the floor to **0.0625**,
above the threshold, and from there no data could have produced a rejection. English tied
once and landed *exactly* on its floor. Planning n against a floor is only sound when the
endpoint is continuous enough for ties to be rare, and lines of code is not. Stated
plainly, because it arrived after the null and that is when such explanations are least
trustworthy: this is a real design defect, not a reason to believe the effect exists.

**The null may simply be true.** The most likely alternative to "underpowered" is
"the sentence does nothing measurable at this size of task", and nothing in this run
distinguishes them. A magnitude-aware test would not automatically have rescued it either
— −12.1% overall in English is carried disproportionately by two tasks.

**A pooled count, recorded and deliberately not used.** Across twelve task-language cells
the sentence produced fewer lines in nine and more in zero, three ties. The
pre-registration forbade pooling as a rescue, and it would be a poor rescue anyway: the
twelve cells are not twelve independent observations, since each task appears in both
languages. It is written down as a lead for a future design with a continuous endpoint and
frozen third-party tasks — not as evidence. The language interaction is flat (English
larger in 2 of 6, p = 0.69).

**The correctness gate was shown to bite.** It passed 48 of 48, which on its own
demonstrates nothing. Four mutations of the two hand-written minimal solutions — nested
dicts replaced instead of merged, an input mutated in place, a length mismatch accepted, a
literal path segment left unchecked — all turn `pytest` red. `analyze_minimal.py` runs that
control on every invocation and asserts on it.

### Third attempt, on tasks nobody here wrote — and the claim is retired

Round 23 said the previous null was hard to read: the fixtures were mine and I knew the
hypothesis, and the endpoint was too coarse for the test. Both were fixed rather than
argued with.

**The tasks come from [MBPP](https://github.com/google-research/google-research/tree/master/mbpp)**
(Austin et al. 2021, CC-BY-4.0) — 974 tasks with prompts, reference solutions and
behaviour-pinning asserts written years before this question existed. The dataset is not
vendored; it is fetched and checked against a hash fixed in the protocol, and a different
hash refuses to run. Twenty tasks are chosen by a rule that never touches an arm: ascending
`task_id`, first twenty whose reference solution has ≥ 12 non-blank lines, imports stdlib
only, and **passes the dataset's own tests** — a positive control that costs the author no
judgement. **The endpoint is characters**, continuous, so the tie hazard that sank the
previous design cannot arise.

40 runs, protocol at `ed366d8` before the data existed:

| | plain | oneline | registered test | result |
|---|---|---|---|---|
| **characters** (primary) | 6,386 | 5,404 | exact paired permutation on task-level proportional deltas | **p = 0.113** |
| non-blank lines (secondary) | — | — | exact sign test, 8 smaller / 4 larger / 4 tied | p = 0.388 |

**The registered prediction failed for the second time, on an independent, third-party
task set.** Per the protocol there is no fourth round, and the claim is retired. The
precise wording matters and round 24 forced it: **no statistically demonstrated effect on
solution size under the tested protocol** — this endpoint, this task subset, this model,
one draw per arm, size measured only on pairs where both arms passed. That is not the same
as "no effect", and this repo does not claim the stronger thing.

**Non-significance is not equivalence, so here is the interval.** The 95% bootstrap CI on
the mean per-task proportional change is **[−18.3%, +0.9%]**. It spans zero, and it also
spans reductions large enough that anyone would want them. The honest label is
**inconclusive against any bound worth setting**, not "the instruction does nothing".

**The pooled number and the per-task number disagree.** Characters fell 15.4% in aggregate
while the sentence was smaller in **8 of 16 tasks** — a coin flip. Two tasks are much of
the aggregate: `mbpp_39` (1,101 → 615 characters, −44.1%, and the only `plain` run that
also spawned an extra file) and `mbpp_34` (−43.8%). But discounting them entirely would be
too convenient, and a leave-one-out check says so: **drop both and the remaining fourteen
tasks still pool to −7.2%.** A panel raised the fairer reading — an instruction that
prevents over-engineering *should* do nothing where nobody over-engineers and a lot where
someone does — and this design cannot separate that story from noise, because there is one
run per cell.

**The correctness gate dropped four pairs of twenty** — `mbpp_60`, `mbpp_122`, `mbpp_136`
failed or produced nothing in both arms, `mbpp_131` in the `oneline` arm — with no
substitution and no rerun, as registered. The size result therefore describes only tasks
both arms could solve, which are the easier ones. What that attrition says about the two
earlier studies where the gate passed 48 of 48 is **nothing**: different tasks, different
gate, and a claim to the contrary was removed from this section after review.

### Both contrasts, every horizon — and the status this result is entitled to

The decision-relevant comparison is not banner-versus-nothing, it is **banner versus a single
sentence**. Both, over full runs and over equal horizons:

| horizon | plain vs mode | | mode vs one-sentence placebo | |
|---|---|---|---|---|
| | delta | p | delta | p |
| full run | **−22.4%** | **0.006** | **−9.2%** | **0.039** |
| 5 turns | −1.9% | 0.77 | −5.5% | 0.77 |
| 6 turns | +0.9% | 0.77 | −7.2% | 0.77 |
| 7 turns | −17.9% | 1.00 | −18.5% | 0.75 |
| 8 turns | −29.3% | 0.29 | −5.5% | 1.00 |

Only the full-run sums reach significance. Every truncated horizon is underpowered — the pair
count falls from 12 to 10 to 8 to 6 as runs are excluded for being too short. The placebo
contrast at least points the same way at every horizon; the plain contrast changes sign at
k = 6. Neither pattern is strong enough to carry a mechanism.

**The status this result is entitled to.** An adversarial panel put it plainly and it is
correct: after six changes of analysis on one dataset, the confirmatory status of this endpoint
is forfeit. What remains is an **exploratory directional finding** — a whole-run output
reduction that reproduces in 11 of 12 pairs against plain and 10 of 12 against the one-sentence
placebo. The **late-onset explanation is a hypothesis chosen after seeing the horizon cells**,
not a demonstrated mechanism, and at least three others fit the same numbers: tail composition,
informative stopping, and leverage from one or two long runs.

To be worth more than that it needs what it does not have: a pre-registered endpoint (paired
total billed output tokens, exact paired permutation test, horizons declared exploratory), a
published per-request ledger with request id, arm, turn index, prompt hash and all four billing
fields, and a rerun on fresh tasks. Until then, treat the direction as suggestive and the
magnitude as unpinned.

### What eight rounds actually say about always-on skills

Three skills, one rig, the same question each time — **does the full block beat one sentence?**

| skill | always on? | verdict |
|---|---|---|
| terse output (4,664 B) | yes, every session | **beats the sentence**: −9.2% output tokens, 10/12, p = 0.039; net **+$14.68**/1k tasks on Opus 5. Its own claim of −65% measured at −22.4%. |
| lazy engineer (5,228 B) | yes, every session | no measurable effect; the sentence beat plain 7/7 and the banner did not beat the sentence |
| systematic debugging (9.4 kB) | no — **0 invocations in 1,409 transcripts** | never beat the sentence in six rounds; costs +51…+84% tokens |

The one sentence of practical advice this supports, and no more than this: **before installing
an always-on instruction block, try writing its intent as one sentence and measure the
difference — on this benchmark the sentence matched or beat two of three blocks, and cost
between 4 and 9 kB less.**

### The same token counts, priced at frontier rates

Rates per MTok from Anthropic's published pricing (retrieved 2026-06-24): Fable 5 $10/$50,
Opus 5 $5/$25, Sonnet 5 $2/$10, Haiku 4.5 $1/$5; 5-minute cache write is 1.25x input, cache
read 0.1x input. Cost = (uncached_in x in) + (cache_write x in x 1.25) + (cache_read x in x
0.1) + (out x out).

Per **1,000 debugging tasks** of the shape measured above:

| model | without the skill | with the skill | difference |
|---|---|---|---|
| Fable 5 | $981.14 | $1,448.65 | **+$467.51** |
| Opus 5 | $490.57 | $724.32 | **+$233.75** |
| Sonnet 5 | $196.23 | $289.73 | **+$93.50** |
| Haiku 4.5 | $98.11 | $144.86 | **+$46.75** |

**This is a rate-card translation, not a prediction.** Every run executed on Haiku 4.5;
the table prices *those* token counts at other models' rates. A different model would emit
different token counts — different tokenizer, different trajectory, different cache
behaviour — so the dollar column answers "what would this measured workload bill at these
rates", never "what Opus 5 would spend".

**And the honest closing note:** this experiment burned roughly 20M tokens in round 1 alone
to evaluate a listing entry worth 116 bytes. As an optimisation exercise it does not pay for
itself. Its value is the method — mechanical scoring, a verified treatment, a positive
control, and a ceiling reported as a ceiling.

## 8. What would falsify this

- Run `tools/extract.py` + `tools/simulate.py` on your own transcripts. If byte-identical
  overwrites are under 2% of overwrites, §3 does not generalise beyond this author's
  sessions and model version — remove the hook. `tools/report.py` prints that verdict
  itself once the field sample is large enough.
- Run `tools/carry.py` on your own transcripts. If Bash and Read are not the top two
  buckets, §1's ranking is local to this setup and the skill's advice is aimed wrong.
- Install the hook and count denials. Zero over a month of real work means the behaviour
  was model-version-specific and the hook is dead weight.
- Toggle a mode banner off for a randomised half of your long sessions and compare
  bytes/turn on its target source. That measures the f in §4, and it can falsify every
  break-even in that table.
- The guard is advisory and racy by construction: it reads the file, then the host
  performs the write. Anything mutating the file in between is outside its knowledge, and
  it cannot be made race-free without owning the write itself.
- **The field rate and the retrospective rate do not measure the same population.** On
  Claude Code 2.1.245 an identical `Write` is denied as designed, but the same write after
  an in-session `Read` of that file bypasses `PreToolUse` entirely — allowed, file mtime
  updated, nothing in the ledger (n=2, one file, one version; mechanism unverified).
  Read-then-overwrite is the common path, so a near-zero field rate is evidence about hook
  reach, not about how often no-op writes happen. Check both: the retrospective number
  comes from transcripts, which record the call regardless. This is the same failure class
  `tools/health.py` exists for — ledger silence is not proof the guard is alive.

## 10. The hook banners cost more than the skill listing

Everyone worries about the skill listing. On this corpus the hooks cost nearly twice as
much.

Fresh run of `tools/carry.py` over every transcript on this host — 1,080 files, 341 sessions
of 50+ turns, 192,752 turns, carry ~42.3 billion token-turns:

| injected source | share of carry | bytes/turn |
|---|---|---|
| `attach:task_reminder` | 4.13% | 66 |
| `attach:skill_listing` | **3.14%** | 43 |
| `attach:hook_success` | 2.90% | 46 |
| `attach:hook_additional_context` | 2.11% | 32 |
| `attach:hook_system_message` | 0.82% | 10 |
| **hook classes combined** | **5.83%** | **88** |

**Hooks are 1.86x the skill listing**, and a third injected source nobody discusses — the
task reminder — outweighs the listing on its own. All three are the same shape of cost:
text injected by the harness rather than by the model or the user, replayed on every
later turn.

This does not retract [section 1](#1-where-the-tokens-actually-go). Pruning the listing is still
the cheapest of the three to act on, because a skill can be set to `user-invocable-only`
in one settings key while a hook has to be justified or deleted. It corrects the *ranking*:
this repo told readers to look at the listing, and the listing is the smallest of the three.

### Scope, honestly

- **Observational, corpus-scale, one host.** Not an experiment: no arms, no pre-registration.
  It is a measurement of what this machine's transcripts contain, and it is reported because
  the measurement is cheap for anyone to repeat — `python3 tools/carry.py <your transcripts>`.
- **This host runs 43 hooks.** A machine with two hooks will not see 5.83%, and the ratio
  is a property of the configuration, not of hooks in general. What transfers is the
  *method*, and the point that injected scaffolding is worth ranking before it is trimmed.
- **The corpus has grown** since the headline figures elsewhere in this document were
  computed (1,316 transcripts, 237,541 turns). This run sees 192,752 turns after the
  50-turn filter and puts Bash at 45.11% against the published 42.5%, Read at 19.83%
  against 21.3%. The published numbers are not restated here and are not superseded by a
  differently-filtered run; the shape is stable, the second decimal is not.
- **Discovered while answering a different question.** The session that produced it was
  routed through Bash for nearly everything, which put its own `Bash` share at 76.8% and
  collapsed `Read` + `Write/Edit` to 0.51% — a reminder that tool-routing policy moves
  carry between buckets without removing it. That n=1 observation is what prompted the
  corpus run; the corpus run is what makes it a finding.
