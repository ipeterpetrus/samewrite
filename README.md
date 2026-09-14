# samewrite

**A token-efficiency skill for coding agents: less context, less tool noise, fewer unnecessary
edits and retries — with result-first human output and evidence-first verification. Measured,
not promised.**

Built from 1,316 Claude Code transcripts (237,541 assistant turns), 462 scored A/B runs, and two
pre-registered pilots of the skill itself (110 + 64 isolated runs). Every number below carries
its label: **MEASURED** (this repo, method published), **OBSERVED** (seen, not controlled),
**DESIGNED** (built, not yet measured), **EXPERIMENTAL** (pilot only, not a claim).

| what | number | label |
|---|---|---|
| where a session's tokens go | Bash + Read results **63.8%** of carry, injected scaffolding 15.3%, prose 5.6%, Write/Edit 9.5% | MEASURED, 1,316 transcripts |
| one terseness sentence vs no instruction | **−22.7%** output tokens (14/16 pairs, p = 0.0001); English replication **−19.6%** (12/16, p = 0.0070); 100% facts kept | MEASURED, pre-registered |
| the same intent as a 4.7 kB always-on block | **−0.8%** vs the sentence (p = 0.86) — the kilobytes do not pay | MEASURED, pre-registered |
| adding an always-on process skill | **+51…+84%** tokens, costlier in 17/18, 18/18, 6/6, 12/12, 4/4, 16/16 pairs | MEASURED, six rounds |
| overwrites byte-identical to disk | **20.8%** (154/741) — the guard hook denies them | MEASURED |
| the popular "≤3 change blocks → Edit" rule | **net negative**; changed-fraction rule keeps 84% of the oracle saving | MEASURED, 20 held-out splits |
| the vNext skill vs the previous one on total context | cheaper on 4/10 fixtures, median +1.4% — **not proven cheaper** | EXPERIMENTAL, 110 runs |
| human-output layer (result first, no filler, detail on request) | per-case contract met 5/8 with the description alone (6/8 before the change), **7/8** with the opt-in one-sentence session hook, 4/8 for the full i-have-adhd hook at 2× the injected bytes; correctness 7/8 in every arm | EXPERIMENTAL, 64 runs, n = 8 per arm |

## Install

```
/plugin marketplace add ipeterpetrus/samewrite
/plugin install samewrite@samewrite
```

Or copy `skills/samewrite/` into `~/.claude/skills/`. That is the whole skill: one listing entry
(~370 characters, carried by every turn) and a 4.7 kB body loaded only when invoked.

Optional, separate on purpose — the guard that denies a `Write` identical to what is already on
disk (read the 60 lines first; it is fail-open and never sends anything anywhere):

```bash
git clone https://github.com/ipeterpetrus/samewrite && cd samewrite
python3 tests/test_write_noop_guard.py     # 64 PASS expected
bash hooks/install.sh                      # registers PreToolUse(Write); backs up settings.json
bash hooks/uninstall.sh                    # removes only samewrite's entry, nothing else
```

## What it saves

The lever order matters more than any single rule. In an append-only, full-replay context
everything you send is billed again on every later turn, so cost is `size × turns remaining` —
the transcript, not the answer, is the bill.

| lever | effect | label |
|---|---|---|
| end the session sooner | −41…−54% of carry when one session becomes two | MEASURED |
| read a range, not a file; ask Bash for the answer, not the log | Read results 21.3%, Bash 42.5% of carry — the skill's first rule | MEASURED share; effect of the rule EXPERIMENTAL |
| prune the skill listing you never invoke | ≈ −3% (72.9% of one listing was never invoked) | MEASURED |
| one terseness sentence | −19.6…−22.7% output tokens | MEASURED |
| do not write files identical to disk | −0.077%, free | MEASURED |
| anchored Edit under ~25% changed, rewrite over ~40% | +0.07% over the rule it replaces | MEASURED |
| root cause before a third speculative patch; verify with a check that can fail | fewer repair loops | DESIGNED |

## How it works

`skills/samewrite/SKILL.md` is the one canonical runtime. On invocation the model gets six short
sections: **context** (expand only to answer an open question; symbol-level tools first when
present), **ask only if material** (CLEAR / MINOR / MATERIAL / CONFLICT), **minimum correct change**
(reuse → stdlib → platform → installed dependency → deletion → new code; never trim security,
validation, compatibility), **root cause with bounded retries** (two failed fixes → stop and
reassess), **verification scaled by risk × uncertainty** (plant a mutation, see RED, restore, see
GREEN), and **output** (below). Nothing is injected every turn; nothing is persisted; there is no
mode to switch.

`hooks/write_noop_guard.py` is the only deterministic piece: byte-exact comparison on raw bytes,
secret-looking paths skipped (the deny/allow answer is an equality oracle), 8 MiB cap, fail-open.

`edit-discipline`, the 1.0.0 skill, is kept as a hidden compatibility alias (`/edit-discipline`
still works; it is not in the model's listing, so it costs nothing per turn).

## Human-friendly output

The skill's output rule, in full: lead with the result, blocker, or next action; numbered steps
only for actions the human must take; report state only when it changed, matters to a decision,
or blocks; errors as the exact failing line, what was observed, one next action; no preamble, no
recap, no generic closer — a complete task ends after its proof; expand fully when explanation,
analysis, a report or detail is requested, and when safety needs the warning.

```text
Fixed the duplicate write path.
Proof: targeted test + typecheck PASS.
Scope: writer.ts · +4/-2.
```

```text
BLOCKED — auth test still returns 200 instead of 401.
Observed: shared middleware is bypassed by the legacy route.
Next: inspect the legacy route registration.
```

The reference for this style is [i-have-adhd](https://github.com/ayghri/i-have-adhd); samewrite
takes the human benefit in ~10% of the text and deliberately drops "restate state every turn"
(state is reported only when it changed or matters). Whether that holds is an EXPERIMENTAL result,
see [Benchmarks](#benchmarks).

## Works with other agent skills

samewrite composes; it does not compete.

| skill | governs | samewrite's stance |
|---|---|---|
| [Ponytail](https://github.com/DietrichGebert/ponytail) | what gets built (YAGNI ladder) | follows its ladder when active, never restates it; never touches `.ponytail-active`, `/ponytail`, `normal mode` |
| [i-have-adhd](https://github.com/ayghri/i-have-adhd) | human-facing interaction style | a stronger presentation profile wins by precedence; samewrite never uses `stop adhd mode` or `normal mode` |
| [Caveman](https://github.com/JuliusBrussee/caveman) | terse wording | same precedence rule; samewrite's text avoids Caveman's trigger words |
| [rtk](https://github.com/rtk-ai/rtk) | Bash output filtering | disjoint hooks (PreToolUse Bash vs Write) |
| [Serena](https://github.com/oraios/serena) | symbol-level navigation | the skill defers to symbol tools on code files when they are loaded |

Proven deterministically (`tests/test_coexist.py`): install and uninstall leave foreign hooks,
status lines, permissions, custom keys and flag files structurally untouched; install twice is a
no-op; malformed `settings.json` is left alone with a warning; the real Ponytail and i-have-adhd
hooks run next to the installed skill without either side changing the other. Ponytail and
i-have-adhd both use `normal mode` as an off-switch; samewrite is not a third claimant — it
has no off-switch to claim.

## Benchmarks

All isolated: a fresh `CLAUDE_CONFIG_DIR` per run, `claude-haiku-4-5-20251001`, pinned flags,
mechanical oracles that were proven to turn RED on planted bad fixtures before any paid run, and
pre-registered contrasts. Infrastructure failures (a missing test runner, a broken transcript) are
classified `INFRA_ERROR` and excluded, never counted as a model failure — the CI run that first
exposed this is in [docs/VNEXT.md §12](docs/VNEXT.md). Losing cases are listed by name in the reports.

- **vNext pilot — HISTORICAL** (`experiments/vnext/`, 11 arms × 10 fixtures, 0 rows excluded): every arm,
  the bare agent included, reached 10/10 correct — the fixtures could not separate arms on
  correctness; the new skill was cheaper than the old one on 4/10 fixtures (median +1.4%) and
  dearer than a one-sentence prefix on 8/10. Verdict **NOT_PROVEN**. Adding the skill to Ponytail,
  i-have-adhd or both lost no correctness. In these runs the skill *body* was invoked 0 times: under
  `claude -p` only the listing entry reaches the model, which is why the human-output rule also
  lives in the listing description.
- **Presentation pilot — HISTORICAL, superseded by the confirmatory run below** (`experiments/presentation/`, 8 arms × 8 adversarial cases including a
  three-turn task and a contradictory-tests blocker): correctness 7/8 in every arm — the shared miss
  is the blocker, where the model edited the contradictory test in all 8 arms. The human-output
  contract held on 5/8 cases with the new description alone (6/8 before), **7/8** with the one-sentence
  SessionStart injection (`SAMEWRITE_OUTPUT_HOOK=1`, opt-in, +163 bytes per session start), 4/8 for
  the full i-have-adhd hook at twice the injected bytes; requested detail stayed full everywhere.
  Verdict **NOT_PROVEN** for the zero-hook default; direction only for the hook.
- **Confirmatory presentation run — CURRENT** (`experiments/presentation/PREREGISTRATION_confirm.md`,
  16 fresh held-out cases, 8 arms, 2 repetitions, frozen before the run): CONFIRM_SUMMARY
- **Earlier rounds** (`experiments/skill-ab/`, 462 scored runs): the terseness sentence
  replicates in two languages; three always-on blocks did not beat one sentence; the
  systematic-debugging skill cost +67.6% tokens and reached the root cause no more often than the
  plain arm.

Method, retractions and every correction: [docs/FINDINGS.md](docs/FINDINGS.md) ·
[docs/VNEXT.md](docs/VNEXT.md) (reference audits of nine repositories at pinned commits,
coexistence matrix, support matrix, release-gate verdict) · pre-registrations next to each rig.

Limits, honestly: one author's sessions, one model family for the transcript corpus, one small
model for the pilots (n = 8–10 per arm — direction, not significance); shares are the claim,
absolute token counts move with language (bytes/3.14 ≈ tokens for English, wrong by ~60% for
Indonesian). Other hosts (Codex, OpenCode, Gemini CLI) get the same body via `adapters/` but are
INSTRUCTION_ONLY and untested there.

## Safety / correctness

- The guard is fail-open on every error path and reads only the file about to be overwritten;
  files whose path looks secret-bearing are skipped entirely.
- No network, no telemetry, no auto-update: pin a commit, read the diff, update on purpose.
- The skill never trims security, trust-boundary validation, required error handling, data
  integrity, accessibility, compatibility or explicit requirements to save tokens, and expands
  when safety needs the warning.
- `PreToolUse` cannot see `@file` mentions, heredocs, `tee` or `sed -i`; the skill covers those
  by instruction only. A `Write` after a `Read` of the same file can bypass the hook on Claude
  Code 2.1.245+ (reproduced; mechanism unverified).

## Development

```
skills/samewrite/           the canonical runtime (edit here; adapters/ is generated from it)
skills/edit-discipline/     hidden compatibility alias for 1.0.0 installs
hooks/write_noop_guard.py   PreToolUse(Write) — deny writes identical to disk
hooks/install.sh · uninstall.sh   idempotent, foreign-preserving, exact-path ownership
tools/adapters.py           generate adapters/ (AGENTS.md / GEMINI.md form); --check fails CI on drift
tools/carry.py · skills.py · prefix.py · bashcost.py · b2t_validate.py · extract.py · simulate.py
                            measure your own transcripts (read-only, stdlib only)
experiments/                skill-ab (462 runs) · vnext (110) · presentation (64) — rigs, fixtures,
                            self-tests, pre-registrations, every run ever scored
docs/VNEXT.md               build report · docs/reference-audits/ nine pinned audits
tests/                      219 assertions in eight suites, mutation-tested; CI on Python 3.9 and 3.12
```

Measure your own sessions — nothing installed, nothing written:

```bash
python3 tools/carry.py --markdown          # carry by source, every Claude Code profile found
python3 tools/skills.py --markdown         # which listing entries you never invoked
python3 tools/prefix.py ~/.claude/projects/*/*.jsonl --min-turns 50   # system prompt + tool schemas
```

`carry.py --history PATH` turns repeated runs into movement (shares and counts only, no content).
Every tool routes through one `scan()`; point it at another agent's JSONL if it logs per-turn
usage, tool calls and replay semantics — the carry model is exact only for append-only,
full-replay contexts.

Run the suites: `python3 -m pip install -r requirements-test.txt` (pytest is the only test-time
dependency; the runtime is standard library) then `for t in tests/test_*.py; do python3 $t; done` —
each file stands alone and exits non-zero on failure. `python3 experiments/vnext/selftest.py` and
`experiments/presentation/selftest_pres.py` prove the benchmark scorers can fail.

Support: none promised. A measurement result with tooling attached, published because the
negative findings are useful.

## License

MIT
