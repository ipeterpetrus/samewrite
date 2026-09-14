# Pre-registration — presentation (human-output) pilot

Written 2026-09-14 before any scored run of this rig. Instruments self-tested first
(`selftest_pres.py`): every prose classifier and every per-case contract turns GREEN on a
planted good answer and RED on a planted bad one.

## Question

Does the compact human-output policy added to the `samewrite` skill (listing description + body
"Output" section) produce action-first, scannable, non-repetitive answers that stay complete when
detail is requested — at no more total cost than SameWrite before this change — and does it
stack with Ponytail and i-have-adhd without contradiction?

Fact that shapes the design: in the previous pilot (`experiments/vnext/runs/pilot1.rescored.jsonl`)
the skill **body was invoked in 0 of 50 samewrite-arm runs** (0 `Skill` tool calls). Under
`claude -p`, only the always-on listing description reaches the model. Two delivery channels are
therefore measured: the description alone (D) and a one-sentence SessionStart injection (Dh, Dm).

## Arms

| arm | contents | always-on samewrite text |
|---|---|---|
| A | bare | 0 |
| B | SameWrite before this continuation (`skill_before/SKILL.md` = commit d4a4c76) | description 330 chars |
| C | i-have-adhd, real `always-on.mjs` + flag | 0 (adhd ≈ 7.2 kB body every session start) |
| D | SameWrite now (new description with the output clause; `edit-discipline` hidden alias) | description 366 chars |
| Dh | D + SessionStart one-liner P2 (`printf` hook) | +170 chars per session start |
| Dm | D + SessionStart one-liner P1 micro | +122 chars |
| E | D + ponytail real hooks | D + ponytail |
| F | D + i-have-adhd real hook | D + adhd |

P2 = "Lead with the result, blocker, or next action. Use numbered steps only for user actions;
omit unchanged state, recaps, and generic closers. Expand when requested."
P1 = "Lead with the result or next action. Keep only information needed to act or verify; expand
when explicitly requested."

## Pins

`claude-haiku-4-5-20251001`; CLI as printed per row; `--permission-mode acceptEdits`, same
`--allowedTools` as the vNext pilot; one fresh `CLAUDE_CONFIG_DIR` per run; cwd under `/tmp`;
multi-turn fixture via `claude -p --continue` in that config; 1 repeat; 8 fixtures × 8 arms.

## Endpoints

1. correctness — mechanical verdict (build: target + hidden neighbour; blocked: tests untouched,
   no false pass claim, contradiction named + next action; text: facts + shape; nochange).
2. `human_ok` — the per-case contract in `fixtures_pres.py` (result-first / numbered human
   actions / blocker with next action / ≥120 words on requested detail / security evidence /
   no state block on a no-op turn / code-only / no manufactured status), each requiring the
   prose to be free of preamble, generic closer and decorative "I did…" steps.
3. cost — output tokens (per turn for the multi-turn case), weighted context, injected bytes.

## Hypotheses (decision rules fixed now)

- H1 D ≥ B on correctness and on `human_ok`; D output tokens ≤ B on the majority of fixtures.
- H2 D ≈ C on `human_ok` (within 1 fixture) at a fraction of C's injected bytes.
- H3 `explain_detail` stays ROOT (≥ 120 words, all facts) in D, Dh, Dm — kill if any of them
  truncates requested detail where B did not.
- H4 E and F: no correctness loss vs D; F does not double status text (state_lines ≤ C's).
- H5 Dh/Dm vs D: if the one-liner does not raise `human_ok` by ≥ 2 fixtures, no hook ships.
- Kill: D loses correctness on ≥ 2 fixtures vs B → NOT_PROVEN for the presentation layer.

n = 8 per arm: direction and instrument validation only; no significance claim will be made.
