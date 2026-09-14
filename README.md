# samewrite

**Token-efficient coding-agent skill that reduces avoidable context, tool noise, edits and retries
while preserving correctness — and measures whether the optimization actually pays.** One canonical
skill, one optional hook, and the measurement tools behind every number here.

**Measured, not promised. Losing experiments stay published.**

| measured fact | number | how |
|---|---|---|
| where a session's tokens actually go | Bash + Read results **63.8%** of carry; injected scaffolding 15.3%; prose 5.6%; Write/Edit 9.5% | 1,316 Claude Code transcripts, 237,541 turns |
| overwrites byte-identical to what is on disk | **20.8%** (154/741) — the guard hook denies them | same corpus |
| one terseness sentence vs no instruction | **−22.7%** output tokens, English replication **−19.6%**, facts kept 100% | pre-registered A/B, 16 pairs each |
| the same intent as a 4.7 kB always-on block | **−0.8%** over the sentence (p = 0.86) | pre-registered A/B |
| this skill vs the previous SameWrite on correctness and cost | non-inferior: 26 vs 25 correct of 32; cost within noise | confirmatory run, 16 fresh cases × 2 reps |

> **Status:** 1.2.0 is on `main` and is what the marketplace path below installs. The skill and
> hooks it ships are byte-identical to 1.1.0 — everything new is the measurement layer, hardened for
> many agents running continuously, and it adds **zero** bytes to what a model reads
> ([release notes](docs/RELEASE_NOTES_1.2.0.md)). Its headline experiment came back
> **NOT_PROVEN**: overall token savings were not established, and that result is published rather
> than buried. Upgrading from 1.0.0 or 1.1.0 is covered in [Install](#install).

## Install

```
/plugin marketplace add ipeterpetrus/samewrite
/plugin install samewrite@samewrite
```

Or copy `skills/samewrite/` into `~/.claude/skills/`. That is the whole skill: one listing entry
of **415 bytes** (~104 tokens), carried by every turn, and a 4.7 kB body loaded only when you type
`/samewrite` or the model decides to invoke it. Measured, not estimated — and in headless
`claude -p` runs the body was invoked 0 times in 174 runs, so for those the 415 bytes is the whole
cost.

Optional, separate on purpose — the guard that denies a `Write` identical to what is already on
disk (60 lines, fail-open, no network):

```bash
git clone https://github.com/ipeterpetrus/samewrite && cd samewrite
python3 tests/test_write_noop_guard.py     # 64 PASS expected
bash hooks/install.sh                      # registers PreToolUse(Write); backs up settings.json
bash hooks/uninstall.sh                    # removes only samewrite's entries, nothing else
```

Upgrading from 1.0.0: `/plugin update samewrite@samewrite`. `/edit-discipline` keeps working as a
hidden alias; rerunning `hooks/install.sh` recognises the 1.0.0 hook entry and adds nothing.

## 30 seconds

```text
you:   test_target.py fails. Fix the bug.

agent: Fixed clamp: min/max were swapped.
       Proof: test_target.py PASS.
       Scope: mod.py · +1/-1.
```

```text
you:   /samewrite refactor the retry loop in fetch.py

agent: (loads the samewrite body once, then works: reads the symbol and its callers, not the
        file; asks only if the change would alter the public API; ends after its proof)
```

## Three ways to run it

| setup | what you get | cost | evidence |
|---|---|---|---|
| **A. SameWrite core** — recommended default | context / edit / retry discipline; result-first answers by description | ~370 chars per turn (listing), body on demand | correctness and cost non-inferior to 1.0.0 (confirmatory run) |
| **B. core + compact human-output hook** — `bash hooks/install.sh --human-output` (or `SAMEWRITE_OUTPUT_HOOK=1`) | one sentence at every session start: result first, numbered steps only for your actions, no filler | ~170 bytes per session start | **NOT_PROVEN** to improve the benchmark (24/32 vs 23/32, p = 1.0); safe, cheap, a preference |
| **C. SameWrite + i-have-adhd** | i-have-adhd's full interaction profile on top | i-have-adhd's ~7 kB per session start | supported coexistence; 23/32 on the same benchmark — not shown to outperform A or B |

None of these is "better". Pick the one you like; the numbers are in [Benchmarks](#benchmarks).

## How it works

`skills/samewrite/SKILL.md` is the one canonical runtime. Its body has six short sections:
**context** (expand only to answer an open question; symbol-level tools first when present), **ask
only if material** (CLEAR / MINOR / MATERIAL / CONFLICT), **minimum correct change** (reuse → stdlib →
platform → installed dependency → deletion → new code; never trim security, validation or
compatibility), **root cause with bounded retries** (two failed fixes → stop and reassess),
**verification scaled by risk × uncertainty** (plant a mutation, see RED, restore, see GREEN), and
**output** (lead with the result, blocker or next action; numbered steps only for actions the human
must take; state only when it changed; no preamble, recap or generic closer; expand fully on request).

Three channels, honestly labelled:

| channel | always on? | measured behaviour |
|---|---|---|
| listing description | yes, every turn (~370 chars) | routing hint; the only always-on text |
| `SKILL.md` body | no — loads on `/samewrite` or when the model invokes it | in 256 headless runs the model never invoked it on its own; `/samewrite` loads it every time |
| deterministic hooks | opt-in, separate install | the no-op-write guard; the optional one-sentence output hook |

`edit-discipline`, the 1.0.0 skill, is a hidden compatibility alias (`disable-model-invocation`): it
costs nothing per turn and the edit rule — identical → do not write; under ~25% changed → Edit; over
~40% → rewrite — lives in `samewrite`.

## Why SameWrite?

Several good projects sit next to this one and ask different questions. None of them is a
competitor, and the differences are easier to use than to argue about:

- **Ponytail** asks: what is the smallest implementation that works?
- **i-have-adhd** asks: how should the interaction feel?
- **rtk** asks: how can command output be reduced before it is read?
- **Serena** asks: how do we navigate code semantically instead of reading whole files?
- **Hermes Agent** is a different kind of neighbour — an agent runtime and skill ecosystem, not a
  competing policy. SameWrite's skill runs inside it (verified below).

**SameWrite asks: what is the cheapest path to a correct, verified result — and can the
optimization prove it pays for itself?** That second clause is the whole difference. Everything
here is measured, the measurements are reproducible from this repository, and the experiments that
lost are published next to the ones that won.

## Experiments that lose stay published

This is a feature, not an apology. A repository that only shows its wins cannot be checked, and a
token-efficiency claim that has never been allowed to fail is not evidence.

| experiment | result | kept because |
|---|---|---|
| a 4.7 kB always-on instruction block vs one sentence | **−0.8%, p = 0.86** — the big block bought nothing | it is the reason the skill body is on-demand and the listing entry is 415 bytes |
| the optional human-output hook | **NOT_PROVEN** over 256 pre-registered runs | it stayed opt-in and off by default instead of shipping on a hunch |
| vNext cost improvement over the previous skill | **within noise** | correctness was non-inferior, so the release shipped on correctness, not on a cost claim |
| `bash-output-shaping`, the strongest candidate the optimizer found | **REJECTED — duplicated by platform behaviour** | 30,731 real Bash results: median 449 B, p90 2,246 B, **none above 30 kB**. The host already caps and spills to a file. See [docs/CANDIDATES.md](docs/CANDIDATES.md) |
| the AI-VOS role matrix, 80 runs on Opus 5 | **NOT_PROVEN** | two byte-identical arms differed by more than any effect measured, so the honest answer is that this rig cannot resolve it at this sample size |

## How it compares

Nine projects, read at pinned commits by read-only audits kept in
[`docs/reference-audits/`](docs/reference-audits/). Every cell below is either something an audit
states or a dash meaning **the audit does not say** — a dash is not a "no". No project is ranked
against another here, because no experiment in this repository compares them head to head.

Legend: ● audited yes · ○ audited no · – not in the audit

| | primary job | always-on cost | mech. hooks | measures itself | evidence loop | presentation | build minimalism | tool-output filtering | symbol navigation | per-scope isolation |
|---|---|---|---|---|---|---|---|---|---|---|
| **samewrite** | cheapest correct, verified change | **415 B** (measured) | ● `PreToolUse(Write)` deny-if-identical | ● pre-registered, scorers self-tested, in CI | ● offline, proposes only | ● one output rule | ○ | ○ | ○ | ● scope / workload |
| [Ponytail](https://github.com/DietrichGebert/ponytail) | YAGNI build ladder | 6,637 B file; injected subset – | ○ text injection only | ● 3 arms × 5 tasks × 3 models, scorer self-test in CI | – | ● self-limited | ● 7-rung ladder | – | – | ○ propagates, not isolates |
| [i-have-adhd](https://github.com/ayghri/i-have-adhd) | ADHD-shaped answers | 7,207 B file; **zero unless a flag file exists** | ○ SessionStart only | ● 84 judged rows; its own gate says FAILED | – | ● | – | ○ | – | ○ no subagent propagation |
| [Caveman](https://github.com/JuliusBrussee/caveman) | terse prose | ~1–1.5k tok/turn (**upstream's own caveat**) | ○ injection + mode regex | ● 3 arms, tiktoken; scorer not self-tested | – | ● | ● separate skill | – | – | per-session |
| [rtk](https://github.com/rtk-ai/rtk) | shrink command output | 8 lines | ● `PreToolUse(Bash)` rewrite, permission-aware | ◐ scorer is `bytes/4`, its own counter untested | – | – | – | ● core, never-worse guard, raw spool | – | – |
| [Serena](https://github.com/oraios/serena) | symbol-level navigation | – | ● read-burst counter → one deny / 120 s | ○ "Why Not Benchmarks?"; agent self-assessed | ● cross-session memories | – | – | ● length ladders | ● the defining feature | per-session / per-project |
| [superpowers](https://github.com/obra/superpowers) | skill library + router | **3,308 B (~800 tok)**, re-injected after `/clear` and `/compact` | ○ one read-only SessionStart | ○ evals live outside the repo | ● plan ledger, failure counters | ● partial | – | ○ file handoff, not filtering | – | ● strongest: subagents inherit nothing |
| [token-savior](https://github.com/Mibayy/token-savior) | symbol index + memory | – | ● three gates, but off / unbundled / inert | ◐ in-repo benchmarks measure index speed; headline retracted by its own README | ● bandit + prefetch | – | – | ◐ PostToolUse, **additive — does not shrink the current turn** | ● | – |
| [aider](https://github.com/Aider-AI/aider) | pair programming with a repo map | 1,024-token repo-map budget | ○ no hooks | ● Exercism harness; no known-good/bad scorer fixture | – | – | – | ○ "no truncation anywhere" | ● tree-sitter + PageRank | – |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | agent runtime + skill ecosystem — a **host**, not a competing policy | **80 B** per unused skill (measured here, 0.21.3 / `1ad89ac`) | ● `pre_tool_call` shell hooks can block and rewrite | – | ● per-skill usage, memories | – | – | – | – | per-profile |

Three things this table will not do:

- **Claim anyone's numbers were verified.** Every audit carries the same line: quoted figures are
  *self-reported and were not re-run*. That includes the numbers in samewrite's own hero table
  until you run `tests/` and `experiments/` yourself, which is why both ship.
- **Treat a file size as a context cost.** Caveman's 7.0 kB and Ponytail's 6.6 kB skill files are
  *level-filtered before injection*, and neither audit gives the filtered size. Only samewrite's
  415 B and superpowers' 3,308 B are measured injected bytes.
- **Hide the audits' limits.** Seven of eight are `SCOPED`: they did not read every file. Only the
  i-have-adhd audit is `FULL`. Caveman's proxy directories — exactly where its −33% input-token
  claim would live — were not opened.

## What is proven, what is not, and what is untested

Three levels, kept apart on purpose. Blurring them is the failure mode this repository exists to
avoid.

| level | claims |
|---|---|
| **measured** | Bash + Read share of carry in the measured corpus · 20.8% of overwrites byte-identical to disk · the terseness experiment's −22.7% output tokens · Hermes: 80 B listing and **0 B** unused body · quality non-inferior on the tested fixtures · the observer adds **zero** default model-context bytes |
| **NOT_PROVEN** | overall end-to-end SameWrite token savings. Observed −1.7%, cheaper on 8 of 10 fixtures, p = 0.109, and smaller than the rig's own measured null-vs-null variance |
| **UNTESTED** | GPT-5.6 Sol portability (the attempt returned 10/10 infrastructure errors) · the observer over native Hermes session history |

## Works with other agent skills

samewrite composes; it does not compete.

| skill | governs | verified composition |
|---|---|---|
| [Ponytail](https://github.com/DietrichGebert/ponytail) | implementation minimalism / YAGNI | follows its ladder when active, never restates it; no correctness loss when stacked; never touches `.ponytail-active`, `/ponytail`, `normal mode` |
| [i-have-adhd](https://github.com/ayghri/i-have-adhd) | interaction / presentation profile | a stronger presentation profile wins by precedence; no correctness loss when stacked |
| [Caveman](https://github.com/JuliusBrussee/caveman) | terse response style | same precedence rule; samewrite's text avoids Caveman's trigger words |
| [rtk](https://github.com/rtk-ai/rtk) | source-side Bash output filtering | disjoint hooks (PreToolUse Bash vs Write) |
| [Serena](https://github.com/oraios/serena) | symbol-level code navigation | the skill defers to symbol tools on code files when they are loaded |

Proven deterministically (`tests/test_coexist.py`): install and uninstall leave foreign hooks,
status lines, permissions, custom keys and flag files structurally untouched; install twice is a
no-op; malformed `settings.json` is left alone with a warning; the real Ponytail and i-have-adhd
hooks run next to the installed skill without either side changing the other. Ponytail and
i-have-adhd both use `normal mode` as an off-switch; samewrite has no off-switch to claim.

## Benchmarks

Four kinds of evidence, answering four different questions:

| kind | what it answers | size | where |
|---|---|---|---|
| transcript observations | where tokens go, what a session carries | 1,316 transcripts | [docs/FINDINGS.md](docs/FINDINGS.md) |
| controlled A/B | does an instruction change output tokens / outcomes | 462 scored runs, pre-registered | `experiments/skill-ab/` |
| historical pilots (superseded) | instrument validation; direction only | 110 + 64 runs | `experiments/vnext/`, `experiments/presentation/` |
| **current confirmatory** | is this release non-inferior, and does the output hook help | **256 runs**, 16 fresh cases × 8 arms × 2 reps, frozen before the run | `experiments/presentation/PREREGISTRATION_confirm.md`, [docs/VNEXT.md §12](docs/VNEXT.md) |

All isolated: a fresh `CLAUDE_CONFIG_DIR` per run, `claude-haiku-4-5-20251001`, pinned flags,
mechanical oracles proven to turn RED on planted bad fixtures before any paid run. Infrastructure
failures (a missing test runner, a broken transcript) are `INFRA_ERROR` — excluded and counted,
never a model failure. Losing cases are listed by name.

**Confirmatory result (current).** Correctness 25–26/32 in every arm, the bare agent included — this
release is non-inferior to 1.0.0 (26 vs 25). The human-output contract (result first, numbered
actions for the human, blocker named, detail on request, no filler) was met on 23/32 runs with the
description alone, 24/32 with the one-sentence SessionStart hook (2 wins, 1 loss, p = 1.0), 23/32
with i-have-adhd's full hook at twice the injected bytes. Hook cost median +1.7%, not significant.
Stacking with Ponytail, i-have-adhd or both lost no correctness. The pre-registered promotion gate
for the hook was **not met**; it stays opt-in. Three cases were floors in every arm (a one-command
follow-up, an out-of-workspace blocker, a public-API rename without alias) and six were ceilings.

**Historical pilots.** vNext pilot: every arm 10/10 correct (ceiling); the new skill not cheaper than
the old (4/10 fixtures). Presentation pilot: 7/8 vs 5/8 for the hook — it did not replicate above.

**Limits.** One author's sessions for the transcript corpus; one small model for the pilots and the
confirmatory run (2 reps: direction, not fine-grained significance); shares are the claim, absolute
token counts move with language (bytes/3.14 ≈ tokens for English, wrong by ~60% for Indonesian);
hidden reasoning tokens are not observable and are not claimed.

## Support matrix

| host | status |
|---|---|
| Claude Code 2.1.270 (skill, hooks, installer) | VERIFIED — headless runs, clean-install and 1.0.0 → 1.1.0 upgrade acceptance |
| Hermes Agent 0.21.3 (`1ad89ac`) — skill via `adapters/hermes/` | VERIFIED — installed into an isolated profile, discovered, listed, loaded, invoked and uninstalled; 11/11 checks |
| Hermes Agent — observer / optimizer | UNTESTED — they run there (ordinary offline Python, exit 0) but have no reader for Hermes session files, so they measure nothing |
| Hermes Agent — Claude Code hooks | NOT_APPLICABLE — `PreToolUse` / `SessionStart` are Claude Code contracts; Hermes' `pre_tool_call` shell hooks are a different surface and none is installed |
| Codex / OpenCode via `adapters/AGENTS.samewrite.md` | INSTRUCTION_ONLY — a verification run on `gpt-5.6-sol` was attempted and returned **10/10 `INFRA_ERROR` (account usage limit)**, so the channel is UNTESTED, not passing and not failing |
| Gemini CLI via `adapters/GEMINI.samewrite.md` | INSTRUCTION_ONLY |
| Pi / OMP | UNSUPPORTED |
| Windows paths | UNTESTED (POSIX paths with spaces and metacharacters are tested) |

**Hermes Agent.** SameWrite's canonical skill is installed and loaded by Hermes without
transformation; the generated adapter differs from the Claude file in one field only, because
Hermes truncates a skill description to 60 characters in its system prompt and the canonical
description is 391. Measured in an isolated profile with no API key set: an **unused** SameWrite
skill costs **80 bytes** in the system prompt and **0 bytes** of body — progressive loading is
real, not claimed. Loading it on demand pulls 4,503 bytes. Reproduce with
`experiments/hermes/acceptance_hermes.py`. Claude Code's hooks are Claude-specific and are not
installed into Hermes.

## Safety / correctness

- The guard is fail-open on every error path, reads only the file about to be overwritten, and
  skips paths that look secret-bearing (the deny/allow answer is an equality oracle).
- No network, no telemetry, no auto-update: pin a commit, read the diff, update on purpose.
- The skill never trims security, trust-boundary validation, required error handling, data
  integrity, accessibility, compatibility or explicit requirements to save tokens.
- `PreToolUse` cannot see `@file` mentions, heredocs, `tee` or `sed -i`; the skill covers those by
  instruction only. A `Write` after a `Read` of the same file can bypass the hook on Claude Code
  2.1.245+ (reproduced; mechanism unverified).
- Measurement stays offline and private: the guard ledger and `carry.py --history` hold sizes and
  shares only — no paths, prompts or content; nothing reads history into the model context; nothing
  rewrites the skill. Evidence-driven optimization, not self-learning.

## Development

```
skills/samewrite/           the canonical runtime (edit here; adapters/ is generated from it)
skills/edit-discipline/     hidden compatibility alias for 1.0.0 installs
hooks/write_noop_guard.py   PreToolUse(Write) — deny writes identical to disk
hooks/install.sh · uninstall.sh   idempotent, foreign-preserving, exact-path ownership; --human-output
tools/adapters.py           generate adapters/ (AGENTS.md / GEMINI.md form); --check fails CI on drift
tools/carry.py · skills.py · prefix.py · bashcost.py · b2t_validate.py · extract.py · simulate.py
                            measure your own transcripts (read-only, stdlib only)
tools/optimize.py           read those aggregates offline: where cost is concentrated, what moved,
                            and whether anything justifies an experiment — or NO_ACTION
                            (--scope-id keeps several agents' populations apart; see docs/MULTI_AGENT.md)
experiments/                skill-ab (462 runs) · vnext (110) · presentation (64 pilot + 256 confirmatory)
                            — rigs, fixtures, self-tests, pre-registrations, every run ever scored
experiments/scale/          how the sweep scales (1k and 10k sessions) and why there is no index
docs/VNEXT.md               build report · docs/RELEASE_NOTES_1.1.0.md · _1.2.0.md · docs/reference-audits/
docs/MULTI_AGENT.md         many agents, running all the time · docs/AI_VOS_PROFILE.md (one profile)
tests/                      416 assertions in eleven suites, mutation-tested; CI on Python 3.9 and 3.12
```

Measure your own sessions — nothing installed, nothing written:

```bash
python3 tools/carry.py --markdown          # carry by source, every Claude Code profile found
python3 tools/skills.py --markdown         # which listing entries you never invoked
python3 tools/prefix.py ~/.claude/projects/*/*.jsonl --min-turns 50   # system prompt + tool schemas
python3 tools/carry.py --history ~/carry_history.jsonl   # append this run; report what moved
```

The optimization loop this repo practises: measure (`carry.py`, the guard ledger) → compare history
(`--history`) → `python3 tools/optimize.py`, which reads those aggregates offline and either says
`NO_ACTION` or names a candidate with the experiment it implies → pre-register and benchmark it
(`experiments/`) → promote by pull request. The optimizer calls no model, opens no socket, injects
nothing into any model's context and never edits `skills/`, `hooks/` or configuration; a canary
secret planted in a transcript, a listing and the ledger is proved absent from every output
(`tests/test_optimize.py`). Full workflow and data contract: [docs/EVIDENCE_LOOP.md](docs/EVIDENCE_LOOP.md);
open candidates: [`experiments/candidates/`](experiments/candidates/). Nothing promotes itself.

## Multi-agent / AI-VOS

SameWrite 1.2 can isolate evidence by role and workload while keeping the observer entirely outside
the model's context — proven empirically, not asserted: across 80 runs of a role matrix on Opus 5,
zero observer artefacts appeared in any transcript.

Generic contract: [docs/MULTI_AGENT.md](docs/MULTI_AGENT.md). One worked profile:
[docs/AI_VOS_PROFILE.md](docs/AI_VOS_PROFILE.md).

Running more than one agent, or running them continuously? Records carry a `--scope-id`, and
populations from different scopes are counted and named but never averaged; evidence that came from
an incomplete sweep cannot produce a candidate; candidate ids are deterministic so a scheduler that
calls this hourly writes no duplicate proposals. Contract, exit codes and the measured resource
budget: [docs/MULTI_AGENT.md](docs/MULTI_AGENT.md).

Run the suites: `python3 -m pip install -r requirements-test.txt` (pytest is the only test-time
dependency; the runtime is standard library) then `for t in tests/test_*.py; do python3 $t; done`.
`experiments/*/selftest*.py` prove the benchmark scorers can fail.

Support: none promised. A measurement result with tooling attached, published because the
negative findings are useful.

## License

MIT
