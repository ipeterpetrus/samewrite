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
