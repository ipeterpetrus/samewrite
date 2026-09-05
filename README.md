# samewrite

**Measure where a coding-agent session's tokens actually go, then test whether the
instructions you install are worth what they cost.**

Built from 1,316 Claude Code transcripts (237,541 assistant turns) and 462 scored A/B
runs. Two of the first edition's three headline numbers were wrong on a 24-transcript
sample, six analysis errors followed, and a pre-registered confirmatory run overturned the
one positive result. All of it is kept in the open in [docs/FINDINGS.md](docs/FINDINGS.md)
— the corrections are the point, not an embarrassment.

**Run it on your own logs** — nothing here is specific to this author's machine:

```
python3 tools/carry.py ~/.claude/projects/*/*.jsonl --markdown
```

That prints your own carry table: which sources occupy your context longest, and what one
session is paying to keep them there. The numbers below are what it printed here; the
interesting question is whether it prints the same shape for you.

**Start here:** the conclusions are directly below · the measured ranking is in
[Where the tokens go](#where-the-tokens-go) · what to run on your own logs is in
[Measure your own sessions](#measure-your-own-sessions) · the method and every retraction
are in [FINDINGS](docs/FINDINGS.md).

## What this repo concluded

Eight rounds of A/B tests, 462 scored agent runs, three always-on instruction blocks, and four
pre-registered runs — one of which replicated and two of which failed. The short version:

1. **Session cost is carry, not output.** In an append-only, full-replay context — which is what every
   agent measured here has — everything you send is billed again on every later turn, so cost is
   `size × turns remaining` and input grows O(N²); both the model and the exponent are
   conditional on that regime, not universal. Output is 0.3% of
   tokens and ~11% of the bill.
2. **The levers are not where the advice points.** Bash and Read results are 63.8% of carry;
   injected scaffolding (skill list, hooks, reminders) is 15.3%; assistant prose is 5.6%; the
   Write/Edit calls that "emit only the changed block" targets are 9.5%.
3. **The popular edit rule is net negative.** `≤3 change blocks → Edit` loses ~79% of the
   available saving on 1,316 transcripts. Changed *fraction* under ~25% is the rule that works.
4. **Skill listings are mostly uninvoked.** 72.9% of one listing (21,891 of 30,009 bytes) had
   never been invoked once across 1,409 sessions — ~6,972 tokens re-sent every turn.
5. **Telling the model to be terse works, and it works the same way in two languages.** One
   sentence against no instruction: **−22.7%** output tokens in Indonesian (14 of 16 pairs,
   exact p = 0.0001) and **−19.6%** in a pre-registered English replication (12 of 16,
   p = 0.0070) — cheaper in **4 of 4 tasks in both**, with 100% of required facts retained
   everywhere. The two sizes are *not* distinguishable (interaction +3.5 pp, p = 0.63), and
   four tasks cannot carry a significance claim of their own, so what replicates is the
   direction. The always-on banner scores −23.4% (15 of 16) against no instruction — a
   different arm, and barely ahead of the sentence.
6. **The kilobytes do not.** Three always-on blocks (9.4 kB debugging, 5.2 kB lazy-engineer,
   4.7 kB terse) were each tested against a one-sentence version of their own intent. **None
   showed a significant advantage over the sentence on a pre-registered test** — at n = 16
   the design detects only d_z ≳ 0.75, so that bounds the advantage rather than excluding
   one. The terse block's advantage measured −9.2% (p = 0.039) on the first task set and
   **−0.8% (p = 0.86) on fresh pre-registered tasks.**
7. **The method is the durable part.** Hidden neighbour tests, a held-out consumer written
   after the patch lands, structural provenance audits (62/62 clean), verified treatment, and
   pre-registered kill conditions — two of three generator hypotheses died by their own
   thresholds, and six analysis errors are documented in sequence rather than tidied away.

The one line of advice it supports: **write the instruction as one sentence, measure it, and
only then consider a kilobyte of rules.**

## Where the tokens go

Token volume across those transcripts:

| bucket | share of volume | share of price* |
|---|---|---|
| `cache_read` | **97.4%** | 68.8% |
| `cache_creation` | 2.2% | 19.7% |
| `output` | 0.3% | 11.5% |
| `input` | 0.0% | 0.0% |

\* cache-read 0.1x, cache-write 1.25x, output 5x the base input rate.

The per-source shares below are **bytes x turns remaining**, converted to tokens by a
constant measured on this corpus — an exposure measure, not a per-source billing readout,
because the API bills one replayed prefix and does not itemise it by source. The bucket
table above *is* real billed usage. Read the split as "what occupies the context", and the
bucket table as "what was charged".

The shares are also **volume within a single billing class**: after turn 1 what is
replayed is billed as `cache_read`, so the 0.1x discount scales every row equally and
cancels out of the percentages. The price column above is where the discount matters, and
it is applied there. The per-request ledger publishes `cache_read` and `cache_creation`
separately, so this is checkable rather than asserted — an early version of this repo did
get it wrong, and [FINDINGS records the correction](docs/FINDINGS.md).

Anything entering the context at turn *i* is replayed on every turn after it. Cost is
**size × remaining turns**, and total session input grows **O(N²)**. What you write
once is cheap; what stays resident is not. So the question worth asking is not "who
generates the most tokens" but "who occupies the context the longest":

| source | share of carry |
|---|---|
| Bash call + result | **42.5%** |
| Read results | **21.3%** |
| injected banners — skill listing, hooks, reminders | **15.3%** |
| Write + Edit calls | 9.5% |
| assistant prose | 5.6% |
| human prompts | 4.2% |

Three consequences, each of which contradicts a popular piece of advice:

- **"Never rewrite a whole file, emit only the changed block."** Aimed at 9.5% of
  carry. Worse, the specific rule this repo used to ship — *≤3 change blocks, use an
  Edit* — is **net negative**: held out across 20 session-level splits it loses ~79% of
  the saving available, because one merged block can span most of a file. The feature
  that works is the **changed fraction**: under ~25% of the file changed → Edit; over
  ~40% → rewrite. That version keeps 84% of the oracle saving, and was never negative
  in 20 splits.
- **"Be terse to save tokens."** Assistant prose is 5.6% of carry. The *scaffolding*
  around the conversation is 15.3% — and the list of installed skills alone (median
  22.8 kB, injected at turn 0 and carried by every later turn) outweighs half of all
  prose. Uninstalling a plugin you do not use is a certain saving; being terser is a
  capped one.
- **"Add a skill for that."** Every always-on instruction block is itself carry.
  [§4 of FINDINGS](docs/FINDINGS.md#4-what-an-always-on-instruction-block-costs) derives
  the break-even — `N* = 2B / (f·s0)` — with measured B and s. This repo's own skill
  does not clear its cost on its edit rule alone; it clears it only by redirecting
  attention to Bash and Read.

### What to do about it, largest effect first

| do this | measured effect | how sure |
|---|---|---|
| **End the session sooner** | **−41…−54%** of carry when one session becomes two | measured on 1,316 transcripts; published work on compaction reports −63…−86% |
| **Prune the skill listing** | **≈ −3%** — 72.9% of it (21,891 of 30,009 bytes) belonged to skills whose **body was never invoked once** | body invocations counted over 1,409 transcripts; a never-invoked description can still be doing routing work, so treat this as an upper bound on waste; cross-checked against the CLI's own token figures, 1.5% apart |
| **Read a range, not a file** | Read results are **21.3%** of carry at a mean of 22.8 kB per call | measured |
| Stop writing files identical to disk — hygiene, not a saving | **−0.077%**, free | 20.8% of overwrites (154/741) were byte-identical |
| Fix the edit rule you were told to use | **+0.07%** — and the popular version (`≤3 change blocks → Edit`) is **net negative** | held out over 20 session-level splits |
| **Tell the model to be terse** — one sentence is enough | **−22.7%** output tokens against no instruction (14/16 pairs, exact p = 0.0001), and **−19.6%** in a pre-registered English replication (12/16, p = 0.0070), with 100% of required facts kept in every arm | pre-registered, fresh tasks, zero exclusions. The 4,664-byte skill that says the same thing beat that sentence by **−0.8%, p = 0.86** — [FINDINGS](docs/FINDINGS.md) |
| *Add a process skill that is never invoked* | **+51…+84% tokens** | six A/B rounds, costlier in 17/18, 18/18, 6/6, 12/12, 4/4, 16/16 pairs |

The last row is not a typo. Adding one always-on instruction was the most expensive thing
measured here, and across five rounds of A/B its benefit appeared on exactly one fixture out
of the five that had any room to show it. In round 5 a **placebo arm** — one sentence urging
care and planning, no mention of root causes — matched the skill's outcome exactly while
costing **63% fewer tokens** than it. Round 6 ran the same three arms over 48 runs: the skill
never beat that sentence, and cost **56% more** than it.

## What the instruction blocks cost

**Verdict first:** on a pre-registered confirmatory run — fresh tasks, one endpoint, one
test, exclusions fixed in advance — none of the three always-on blocks showed a significant
advantage over a one-sentence version of its own intent. With 16 pairs the design detects
only d_z ≳ 0.75: that bounds the advantage, it does not establish equivalence. The terse
block went from −9.2% (p = 0.039) on the first task set to **−0.8% (p = 0.86)** on fresh
tasks. Terseness replicates; the kilobytes do not.

These are **two contrasts inside one experiment**, not two independent findings: the same
48 runs supply both the presence effect (sentence versus none, −22.7%; banner versus none,
−23.4%) and the length effect (block versus sentence, −0.8%). They share an error structure and should be read
together — a reader who counts them as separate confirmations is double-counting.

This is the other half of the question: what does it cost to *add* an
instruction? `systematic-debugging` is a skill whose whole promise is "find the root cause
before fixing". Two arms, same bug fixtures, one sentence apart — the second invokes the
skill. Scoring is mechanical (a hidden neighbour test catches symptom-only fixes), the
treatment is verified in the transcripts (36/36 skill-arm runs really did load the skill;
0/36 plain-arm runs did), and a golden fix was applied first to prove the target score was
reachable at all.

Per **1,000 debugging tasks**, pricing the measured token counts at published rates:

| model | without the skill | with the skill | difference |
|---|---|---|---|
| Fable 5 | $981.14 | $1,448.65 | **+$467.51** |
| Opus 5 | $490.57 | $724.32 | **+$233.75** |
| Sonnet 5 | $196.23 | $289.73 | **+$93.50** |
| Haiku 4.5 | $98.11 | $144.86 | **+$46.75** |

**+67.6% tokens in round 2, costlier in 18 of 18 paired runs** (two-sided sign test
p ≈ 0.00001); round 1 measured +79.9% on a different fixture set. In both rounds the plain
arm reached the root cause in **35 of 36 runs** — a ceiling, so the benefit could not be
measured at all.

Round 3 built the headroom on purpose, with the protocol written down first and two
mechanical controls (a root fix must satisfy everything; a shortcut patch must satisfy the
target and break the hidden neighbour). Round 4 turned the difference into a pre-registered
generator hypothesis with a kill condition — and **the kill condition fired**: two of five
fixtures came back at the ceiling, so the hypothesis is published as wrong.

The same round found the first thing the skill demonstrably does. On the one fixture whose
root fix lives in **a single shared helper**, the control arm reached the root cause **0 of
4** times — it guarded the call site the failing test named and left three sibling callers
broken — while the skill arm reached it **4 of 4**, guarding the helper. On the two fixtures
whose "root" was N data rows or N copy-pasted functions, the skill did nothing. Pooled, that
is p = 0.375: not significant, and reported as not significant.

And before any of it was believed, the oracle was audited: for every `ROOT` verdict ever
scored, did the file containing the root cause actually change? **28 of 28 did.** Full method, both rounds, and the
reasons the dollar column is a rate-card translation rather than a prediction:
[§9 of FINDINGS](docs/FINDINGS.md#9-what-an-always-on-skill-costs-measured-twice).

## Before and after: what this repo got wrong

The first edition read 24 transcripts. It is kept here on purpose, because the corrections
are the useful part.

| claim | first edition | after 1,316 transcripts |
|---|---|---|
| where carry goes | Write calls **25.4%** | Write+Edit **9.5%**; Bash 42.5%, Read 21.3% |
| change blocks per rewrite | **6.9** | **2.6** (median 2) |
| the edit rule | "≤3 blocks → Edit" | that rule is **net negative**; use changed fraction <25% |
| identical overwrites | 15% (18/122) | **20.8%** (154/741) — the one finding that held |
| skill listing | not measured | **72.9% never invoked**, ~3% of session carry |
| "never invoked = free to remove" | implied | **wrong** — a description steers without being loaded |

## Compatibility

| piece | needs | portable? |
|---|---|---|
| `hooks/write_noop_guard.py` | Claude Code `PreToolUse` hook protocol — JSON on stdin with `tool_name`/`tool_input`, a `hookSpecificOutput.permissionDecision` on stdout | **Claude Code only** as written; the logic is 60 lines and the contract is one function |
| `tools/carry.py`, `skills.py`, `extract.py`, `simulate.py` | transcript JSONL with per-turn `usage` and `tool_use`/`tool_result` blocks | any agent that logs those — see below |
| `experiments/skill-ab/` | a headless agent invocation and a per-session config directory | any CLI agent with both |
| everything | **Python 3.8+, standard library only** | `tiktoken` is optional in `extract.py` (falls back to bytes/3.14); `pytest` is only used by the experiment fixtures |

Verified here: 92 assertions across four suites pass on CPython 3.10; CI runs 3.9 and 3.12. No
walrus operator, no `match`, no third-party runtime dependency. 45 files, 516 KB.

## Using it with another agent

The Claude-Code-specific part is smaller than it looks. Every transcript tool routes through one
function — `scan()` — which turns a log file into `(turn_index, size_in_bytes, source_label)`
triples plus a usage counter. Point that at another agent's logs and the same arithmetic runs —
but **the carry model is exact only for append-only, full-replay contexts.** Anywhere else it is
a linear-replay *upper bound*, not a measurement, and must be labelled that way.

What an agent must log for the tools to apply:

- a **per-turn boundary** (something that marks one model call),
- **token usage per turn** — at minimum output, ideally the cache-read/cache-write split, without
  which the carry model degrades to a byte estimate,
- **tool calls and their results**, distinguishable by tool name, since that is the whole point of
  the carry table,
- and the one that is easy to forget: **verified replay semantics.** A transcript records what
  was *written*, never what was *sent*. A rolling-summary agent, an agent with a fixed prompt, or
  one that branches into sub-agents can satisfy the first three requirements and still produce a
  carry table that means nothing. Either the replay behaviour is documented, or the log carries
  per-inference inclusion intervals — `(item_id, first_included_turn, last_included_turn)`.

### A port that failed, and why that is the useful part

The first agent this was pointed at — a workflow-based research/trading agent running on the
same machine — **could not be measured by these tools at all**, and the reason generalises.

Its log is 4,757 records of `ts, event, goal, usd, model, area, topic`. It has **no turn
boundary, no tool-call labels, and no token usage** — the check for all three came back false.
What it does have is `usd` per event, recorded directly: ~$13 of model spend across 2.5 months,
`cx/gpt-5.5` $10.76, `cx/gpt-5.6-terra` $2.14, `ds/deepseek-v4-flash` $0.02. (A fourth
`budget_record` event carries another $41 with no model attached and looks like a rollup of the
same spend, so treat any total that sums all of them as double-counted.)

The deeper point is not the missing fields. **That agent has no carry**, because it has no
replayed transcript: each step is an independent call, its cost is linear in the number of
events, and nothing from step 3 is re-billed at step 40. The `size × turns remaining` model —
the thing this whole repo rests on — simply does not describe it.

So the honest scope is narrower than the requirements list above suggests:

| agent shape | does carry apply? | what to measure instead |
|---|---|---|
| linear replayed transcript (Claude Code, most CLI coding agents) | **yes** — this is the O(N²) regime the tools model | carry by source, exactly as here |
| server-side compaction / context editing / pruned tool results | **partly** — replay is truncated, so carry is an upper bound | measure billed input per turn against cumulative transcript size, as [FINDINGS §7](docs/FINDINGS.md) does |
| event- or workflow-based, fresh context per step | **no** — cost is linear in steps | per-event cost, which such agents usually already log |

The three requirements are **necessary, not sufficient**: a log can satisfy all of them and
still produce a meaningless carry table if the runtime does not actually replay what the log
records. Check the regime before the fields.

If a log has the boundary and the tool calls but no usage, `carry.py` still produces a
**byte-volume ranking**. Call it that and nothing more: it supports no token-share claim and no
dollar claim, because bytes and tokens do not rank alike — token-dense content such as hashes,
base64 and minified payloads is *undercounted* by bytes, and the size of that distortion is
tokenizer-specific and unmeasured here.

For an agent that has no pre-write hook at all, the guard does not port, but its finding does:
**20.8% of overwrites in this corpus rewrote a file byte-for-byte identically.** That check is
four lines in any write path, hook or not.

And the experiment rig is agent-agnostic by construction. Its oracles are files on disk and its
statistics are paired sign and exact permutation tests — nothing in
`experiments/skill-ab/` knows which model produced the patch. Swapping the launcher line is
enough to point it at a different agent, which is how any claim in a system prompt should be
checked before it is installed.

## What's here

Every run this repo has ever scored is published, classified, and reconciled in one
table: 48 pre-registered confirmatory runs, 294 exploratory ones, 95 calibration runs, and
654 quarantined lines from an execution that was accidentally launched twice. See
[`experiments/skill-ab/runs/`](experiments/skill-ab/runs/). The classification is not prose:
`manifest.json` marks each file's evidence class and `load.py` refuses to load anything that
is not analysis-eligible. One file in twenty loads without a guard — the confirmatory run,
which is what the conclusions rest on. The exploratory rounds are the path that led there,
not evidence; a number that appears only in them is a lead.


```
hooks/write_noop_guard.py   PreToolUse(Write) — deny writes identical to disk
hooks/install.sh            one command, idempotent, backs up settings.json
skills/edit-discipline/     when to anchor-edit vs rewrite whole (Claude Code skill)
tools/carry.py              carry by source over your own transcripts — the table above
tools/skills.py             price your skill listing: which entries you have never invoked
                            (cross-check it against the CLI's own /skill-doctor)
tools/extract.py            pull carry data out of transcripts (redacted by default)
tools/simulate.py           robustness suite: jackknife, bootstrap, holdout, drop-top-k
tools/report.py             read the field ledger: how often the guard fires, and how
                            many rewrites would have fit in an Edit
tools/feed.sh               regenerate docs/FIELD_DATA.md from the ledger, commit if changed
tools/health.py             is the guard still installed? ledger silence proves nothing on
                            its own, so compare it against session activity
tests/                      92 assertions in four suites, mutation-tested
docs/FINDINGS.md            full numbers, method, the corrections, and what an
                            adversarial panel broke before publication
```

## Status: experiment, not a default

An adversarial review panel held this back until the security boundaries and the
reproduction artifacts existed. They now do — but the honest framing survived the
review: this is an **optional experiment**, not a hook anyone should adopt by default.
Its load-bearing findings come from one author's sessions on one model family (August
2026). Measure your own before trusting it; every tool needed to do that is in here,
and [§8](docs/FINDINGS.md#8-what-would-falsify-this) says what result should make you
delete it.

## Install the hook

```bash
git clone https://github.com/ipeterpetrus/samewrite && cd samewrite
python3 tests/test_write_noop_guard.py     # 51 PASS expected
bash hooks/install.sh
```

Takes effect in the next session — `settings.json` is read at startup.

The installer wires an optional field ledger (`SAMEWRITE_LEDGER`, default
`~/logs/samewrite.jsonl`). It records **size and outcome only** — never a path, a
filename, or file content — so the claim in this README can be checked against what
actually happens rather than re-argued:

```bash
python3 tools/report.py ~/logs/samewrite.jsonl
python3 tools/report.py ~/logs/samewrite.jsonl --markdown > docs/FIELD_DATA.md
```

The retrospective number is 20.8% of overwrites. If your field rate lands under 2% over
a few hundred writes, the finding did not generalise — `report.py` says so itself, and
the right move is to remove the hook.

## Measure your own sessions

```bash
python3 tools/carry.py ~/.claude/projects/*/*.jsonl --markdown
python3 tools/skills.py ~/.claude/projects/*/*.jsonl --markdown
python3 tools/extract.py mine.pkl ~/.claude/projects/*/*.jsonl
python3 tools/simulate.py mine.pkl
```

`carry.py` and `skills.py` read sizes, tool names and skill names only — no path,
prompt, file content, or tool output is stored or printed.

`extract.py` is **redacted by default**: every line of every file is replaced with an
8-byte hash plus its token count, computed during extraction. That is enough for
`difflib` to find the same change blocks and enough to price them, while storing not one
character of your code. Paths, prompts, and tool output are never stored at all.

Redaction was not free to discover — the first version of this repo stored raw file
contents while the README claimed it did not. Re-running all 50 simulations on redacted
data moved the headline number by 0.001 pp (0.076% → 0.077%), so the privacy-preserving
path costs nothing in fidelity.

`--keep-content` turns redaction off for deeper analysis. Output then contains your file
contents verbatim. Do not share it.

## Security and support

The hook is code that runs on every `Write` in your session. Read it before installing —
it is 60 lines. It is **fail-open** on every error path, never writes, never sends
anything anywhere, and reads only the file the agent was about to overwrite.

Set `SAMEWRITE_ALLOW_NOOP=1` when an identical write is deliberate — refreshing mtime,
triggering a file watcher, testing idempotency.

Do not wire `git pull` into an auto-update for this hook. A hook that updates itself from
a remote repository is a code-execution path into your machine. Pin a commit, read the
diff, then update on purpose.

**Support: none promised.** This is a measurement result with tooling attached, published
because the negative findings are useful, not because it is a maintained product.

## Honest limits

- **Every A/B run in this repo except one was conducted in Indonesian.** The task prompts, the
  one-sentence placebos and the substance-gate patterns are all Indonesian; the write-up
  is English. That matters most for the terseness result, whose endpoint is output
  *tokens* and whose languages do not tokenize alike, and least for the line-count
  results. The terseness contrast now has a pre-registered English replication and holds
  there (−19.6%, p = 0.0070); every other English phrasing quoted here is still an untested
  translation of the string that was measured.
- **The minimal-change sentence failed two pre-registered tests and is retired.** Six
  author-written tasks in two languages (p = 0.0625 / 0.125), then twenty frozen
  third-party MBPP tasks with a continuous endpoint and a mechanical selection rule
  (**p = 0.113**; smaller in 8 of 16 tasks, a coin flip). Per the protocol there is no
  third attempt: **no statistically demonstrated effect under the tested protocol** — which
  is not the same as no effect, since the 95% CI on the mean change is [−18.3%, +0.9%] and
  is inconclusive rather than empty. The 7-of-7, p = 0.016 figure that circulated before is
  exploratory and superseded.
- The saving is 0.077% (identical writes) plus at most 0.086% (an oracle edit policy;
  the deployable fraction rule reaches ~0.072% of that). Everything here is ~0.1%.
- The guard is **fail-open** on every error. It saves tokens; it does not prevent harm.
  A bug in it must never block real work.
- `PreToolUse` cannot see `@file` references (they enter context without a tool call),
  nor `cat > f` heredocs, `tee`, or `sed -i`. The skill covers those by instruction only.
- **The guard has a blind spot over its own target case.** On Claude Code 2.1.245, a
  `Write` of byte-identical content is denied normally — but if the agent has `Read` that
  file earlier in the session, the same identical `Write` executes with the hook never
  running at all. Reproduced twice on one file: no `Read` → denied, ledger records the
  check; after a `Read` → allowed, file mtime updates, ledger records nothing. The
  mechanism is unverified (it looks like a fast path taken when the tool already holds
  current file state), but the consequence is not: read-then-overwrite is the ordinary
  workflow, so a low field-denial rate is partly this, not partly absence of no-ops.
  Transcript analysis (`tools/extract.py`) is unaffected — it counts the tool call either
  way, which is why the retrospective rate is 20.8% while the field rate is far lower.
- The changed-fraction rule is computed from the finished replacement, so an agent
  applies it as an estimate, not a measurement. Its sample is also 587 cases where the
  model had already chosen to Write.
- Byte-exact comparison on **raw bytes**. An earlier version read in text mode, which
  silently folds CRLF into LF — it would have blocked a legitimate line-ending
  normalisation. Found by cross-family audit, not by the test suite.
- Files whose path looks secret-bearing are skipped entirely. Not because the guard leaks
  contents — it never reads them out — but because deny/allow is an **equality oracle**:
  a caller could guess a file's contents and read the answer off the verdict.
- Session length dominates everything here. Literature puts compaction at −62.8…−85.9%;
  splitting a session in two measures at −41…−54% on this data. This repo is worth ~0.1%.
  Do not mistake it for the lever.

## License

MIT
