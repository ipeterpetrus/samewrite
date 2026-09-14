# samewrite

**Token-efficient coding-agent skill for Claude Code: reduce context, tool noise, unnecessary
edits and retries while preserving correctness and evidence.** One canonical skill, one optional
hook, and the measurement tools behind every number here — including the experiments that lost.

| measured fact | number | how |
|---|---|---|
| where a session's tokens actually go | Bash + Read results **63.8%** of carry; injected scaffolding 15.3%; prose 5.6%; Write/Edit 9.5% | 1,316 Claude Code transcripts, 237,541 turns |
| overwrites byte-identical to what is on disk | **20.8%** (154/741) — the guard hook denies them | same corpus |
| one terseness sentence vs no instruction | **−22.7%** output tokens, English replication **−19.6%**, facts kept 100% | pre-registered A/B, 16 pairs each |
| the same intent as a 4.7 kB always-on block | **−0.8%** over the sentence (p = 0.86) | pre-registered A/B |
| this skill vs the previous SameWrite on correctness and cost | non-inferior: 26 vs 25 correct of 32; cost within noise | confirmatory run, 16 fresh cases × 2 reps |

> **Status:** 1.1.0 is on `main` and is what the marketplace path below installs. 1.2.0 is in
> review: the skill and hooks are byte-identical to 1.1.0, and everything in it is the measurement
> layer hardened for many agents running continuously ([release notes](docs/RELEASE_NOTES_1.2.0.md)).
> Upgrading from 1.0.0 is covered in [Install](#install).

## Install

```
/plugin marketplace add ipeterpetrus/samewrite
/plugin install samewrite@samewrite
```

Or copy `skills/samewrite/` into `~/.claude/skills/`. That is the whole skill: one listing entry
(~370 characters, carried by every turn) and a 4.7 kB body loaded when you type `/samewrite` or when
the model decides to invoke it.

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
| Codex / OpenCode via `adapters/AGENTS.samewrite.md` | INSTRUCTION_ONLY — generated from the skill, not run there |
| Gemini CLI via `adapters/GEMINI.samewrite.md` | INSTRUCTION_ONLY |
| Pi / OMP | UNSUPPORTED |
| Windows paths | UNTESTED (POSIX paths with spaces and metacharacters are tested) |

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
tests/                      400 assertions in eleven suites, mutation-tested; CI on Python 3.9 and 3.12
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
