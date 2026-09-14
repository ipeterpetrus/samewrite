# Pre-registration — SameWrite vNext pilot (arms A–J)

Written 2026-09-14 before any scored run. A single smoke run (arm A, fixture `oneline`) was
allowed before this file only to prove the pipeline authenticates, produces a transcript and
extracts metrics; its result is not analysis-eligible.

## Question

Does the vNext runtime core (`skills/samewrite/SKILL.md`, ~80-token listing entry always on,
~2.3 kB body on demand) beat current SameWrite (`edit-discipline`) on **correct result per
weighted context token**, and does adding it to Ponytail / i-have-adhd leave their correctness
untouched while not raising cost?

## Arms (master prompt §28)

| arm | config dir contents | prompt |
|---|---|---|
| A | empty settings, no skills | task |
| B | as A | `Answer as briefly as possible, without reducing the technical content.` + task |
| C | `skills/edit-discipline/` | task |
| D | `skills/samewrite/` | task |
| D2 (secondary) | D + `write_noop_guard.py` PreToolUse + `samewrite_mode.py` SessionStart core line | task |
| E | ponytail@e3ba2aa real hooks (activate / mode-tracker / subagent) | task |
| F | i-have-adhd@4092de0 real `always-on.mjs` + `.i-have-adhd-always` flag | task |
| G | E + F | task |
| H | D + E | task |
| I | D + F | task |
| J | D + E + F | task |

No Caveman / RTK / Serena arms: their mechanisms (presentation compression, Bash-output
rewriting, LSP navigation) are not what the fixtures below measure.

## Pins

- model `claude-haiku-4-5-20251001` (the model every earlier round in this repo used; cost)
- CLI: whatever `claude --version` prints, recorded per row (`cli` field); 2.1.270 at writing
- `--permission-mode acceptEdits --allowedTools "Bash(python3:*),Bash(pytest:*),Bash(python:*),Read,Edit,Write,Grep,Glob"`
- `CLAUDE_CONFIG_DIR` = fresh per-arm directory built by `rig.py build_cfg()`; cwd = temp dir
  under `/tmp` (no CLAUDE.md / AGENTS.md anywhere above it); env stripped of `CLAUDE*`/`SAMEWRITE*`
- fixtures: the 10 in `fixtures.py` at the commit this file lands in; oracles self-tested by
  `selftest.py` (48 checks: golden → ROOT, symptom → SYMPTOM, untouched → FAIL, edited test → INVALID)
- trials: **1 repeat per (arm, fixture)** — 11 arms × 10 fixtures = 110 runs. This is a pilot.
- timeout 420 s per run; a timeout is a FAIL and is reported, never dropped

## Endpoints

Primary (mechanical):
1. **correctness** — verdict `ROOT` (build: target + hidden neighbour green; nochange: file
   untouched, and a question asked where `must_ask`; text: all facts + shape contract).
2. **weighted context** — `input + 1.25·cache_creation + 0.1·cache_read` tokens from the
   session transcript (the repo's published rate weights), summed over the run.

Secondary: output tokens, tool-result bytes by source (Read / Bash / Write-Edit), turns, tool
counts, files changed, diff LOC, whether the final message asks a question, wall seconds.

## Hypotheses and decision rules (fixed now)

- H1 (candidate vs current): D has ≥ C's ROOT count over the 10 fixtures, and lower weighted
  context on the majority of fixtures where both are ROOT.
- H2 (coexistence, correctness): H ≥ E, I ≥ F, J ≥ G in ROOT count. Any drop of ≥ 2 fixtures
  is a **material correctness regression → do not ship**.
- H3 (coexistence, cost): adding D to E/F/G does not raise weighted context on a majority of
  paired fixtures.
- H4 (persistence tax): D2 costs more weighted context than D on a majority of fixtures
  (expected; if D2 is also not more correct, the hooks stay opt-in).
- Kill: D fewer ROOT than C by ≥ 2 → NOT_PROVEN, candidate rejected on this evidence.

Statistics: paired sign test per contrast over fixtures (exact binomial, two-sided). With
n = 10 pairs the smallest attainable two-sided p is 0.002 (10/10) and 7/10 gives p = 0.34; the
pilot **cannot** establish significance for a moderate effect. It estimates effect direction
and size and validates instruments. A confirmatory run needs ≥ 16 pairs and fresh fixtures.

## Validity gates (a row failing any is excluded and counted in the report)

- `treatment_ok` — transcript contains the arm's expected banner/listing and **no** foreign
  banner (`PONYTAIL MODE ACTIVE`, `ADHD MODE ACTIVE`, `CAVEMAN MODE ACTIVE`, samewrite core line,
  `superpowers`); arms A/B must contain no skill listing at all.
- `rc == 0` and a transcript was found.
- `INVALID` (agent edited `test_target.py`) is reported as a failure, not excluded.

## What this pilot cannot say

- Nothing about Fable/Opus/Sonnet behaviour — one model, rate-card translation only.
- Nothing significant at n = 10; losing fixtures will be listed by name.
- Nothing about OpenCode / Pi / Codex hosts — INSTRUCTION_ONLY, untested.
