# SameWrite vNext — build report (2026-09-14)

Status line for this iteration is in [§9](#9-release-gate-and-status). Everything below is
either measured here, labelled `EXTERNALLY_REPORTED`, or labelled `UNTESTED`.

## 1. What changed

| piece | before | after |
|---|---|---|
| runtime core | `skills/edit-discipline/SKILL.md` only (2,997 B; edit rule + carry table) | **`skills/samewrite/SKILL.md`** (canonical, 4.4 kB body on demand, ~330-char listing entry always on) + `edit-discipline` kept unchanged for compatibility |
| controls | none | `/samewrite on|off|status`, `stop samewrite` — whole-message match, namespaced; **never** `normal mode` / `stop ponytail` / `stop caveman` / `stop adhd mode` |
| hooks | `write_noop_guard.py` (PreToolUse Write) | guard unchanged in behaviour + honours `samewrite-disabled`; new **opt-in** `samewrite_mode.py` (UserPromptSubmit switch, SessionStart one-line core only with `SAMEWRITE_CORE=1`) |
| install | `hooks/install.sh` (guard only) | same default; `SAMEWRITE_MODE_HOOK=1` adds the switch; paths now `printf %q`-quoted; new `hooks/uninstall.sh` removes only SameWrite-owned entries |
| adapters | none | `tools/adapters.py` generates `adapters/AGENTS.samewrite.md` + `GEMINI.samewrite.md` from the canonical body; CI fails on drift |
| tests | 6 suites / 161 assertions | 9 suites (see [§7](#7-verification-actually-run)) |
| benchmark | `experiments/skill-ab/` | + `experiments/vnext/` (arms A–J, self-tested oracles, contamination check, pre-registration) |
| version | 1.0.0 | 1.1.0 (plugin.json = marketplace.json = hook `VERSION`, pinned by test) |

Layering (master prompt §6): the skill body owns **work policy** (context ladder, information-gain
gate, ambiguity classes, minimum correct change, root-cause + two-failed-fixes stop, risk ×
uncertainty verification, exit receipt). **Build policy** defers to an active minimalism profile
("If a minimalism profile such as Ponytail is active, follow its ladder and do not restate it").
**Presentation** is inherited: `system/safety > explicit user format > active presentation
profile > this file`. There is no always-on SameWrite block by default; the SessionStart
one-liner is opt-in and measured as arm D2.

Not built (deliberately): a status line (no demonstrated value; both Ponytail and Caveman already
contend for the single `statusLine` slot), a SubagentStart injection (subagents get nothing
unless the parent passes it), session-scoped vs durable mode split (the marker is durable until
`samewrite on`; a session-scoped variant needs per-session files + GC and has no measured
benefit yet), the evidence spool (§19 — see [§6](#6-mechanisms-evaluated)), an AI-VOS profile.

## 2. Reference audits (commit pins, licenses, coverage)

All clones read-only, depth-1, 2026-09-14. Full path:line reports: [`docs/reference-audits/`](reference-audits/).

| repo | commit | license | tracked files | read fully | audit label |
|---|---|---|---|---|---|
| ipeterpetrus/samewrite (target) | `0aec7ce5fdf5acdfdfe39de01e912e2ad6aa5334` | MIT | 89 | README, skill, hooks, tests, CI, rig | SCOPED |
| ayghri/i-have-adhd | `4092de07ce3ed88389d77c0d623b7af89b40ac0e` | MIT | 64 | 63/63 non-binary | **FULL** |
| DietrichGebert/ponytail | `e3ba2aa6f1e6f0bc4d69eb09c9f0d0a93af56156` | MIT | 166 | 53 | SCOPED |
| JuliusBrussee/caveman | `15581d14007fd01fb3f132016741962f34936ca2` | MIT (+BSL for engine/proxy dirs) | 1388 | 18 | SCOPED |
| rtk-ai/rtk | `d402152ffa050ca3753672e3d49c3f2ff498a07b` | Apache-2.0 | 577 | 13 | SCOPED |
| oraios/serena | `403ad0a562bbc86ff5a0e26c23544dbd99235c15` | MIT | 1065 | 3 (+13 partial) | SCOPED |
| Mibayy/token-savior | `73e9c7f56fd7cd40ecc72cdc4b032264018f8b4f` | MIT | 473 | 9 | SCOPED |
| obra/superpowers | `b36e0829c6d0140e93cfef2ca599b1b07d4a7797` | MIT | 195 | 17 | SCOPED |
| Aider-AI/aider | `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | Apache-2.0 | 691 | 1 (+13 partial) | SCOPED |

Ponytail historical pin `356918eb…` → HEAD `e3ba2aa`: 23 files, +871/−28 — one feature (Cursor
native hooks) plus a version bump to 4.10.0; nothing in the mechanisms listed in master prompt §4
changed (`docs/reference-audits/ponytail.md`, PIN-DIFF).

**No code was copied from any reference.** Mechanisms were re-implemented from the audited
behaviour; Apache-2.0 sources (rtk, aider) contributed ideas only, so no NOTICE obligation arises.

## 3. Coexistence surface (what SameWrite must not touch, with evidence)

| plugin | off-phrase(s) | state files | commands | source |
|---|---|---|---|---|
| Ponytail | `stop ponytail`, `normal mode` — whole message, trailing punctuation stripped | `$CLAUDE_CONFIG_DIR/.ponytail-active`, `.ponytail-statusline-nudged`, `~/.config/ponytail/config.json` | `/ponytail*` (prefix regex `^[/@$]ponytail`) | hooks/ponytail-config.js:40-43, ponytail-runtime.js:31-44, ponytail-mode-tracker.js:44-54 |
| i-have-adhd | `stop adhd mode`, `normal mode` — prose-honoured on Claude Code, mechanical only on Pi | `$CLAUDE_CONFIG_DIR/.i-have-adhd-always` | `/i-have-adhd` | skills/i-have-adhd/SKILL.md:19, hooks/always-on.mjs:16-20, extensions/i-have-adhd.ts:27 |
| Caveman | `stop caveman`, prompt-initial `normal mode`, plus brevity words (`be brief`, `less tokens`, …) **activate** it | `.caveman-active`, `.caveman-sessions/`, `.caveman-mode-log.jsonl`, `~/.config/caveman/` | `/caveman*`, `cavecrew-*` agents | src/hooks/caveman-parse.js:93-256 |
| rtk | none (event-driven) | `~/.config/rtk/`, `~/.local/share/rtk/`, `~/.claude/RTK.md` | `rtk …`, PreToolUse(Bash) | src/hooks/hook_cmd.rs:595-603 |
| superpowers | none (no toggle) | `.superpowers/`, `docs/superpowers/` | skill namespace `superpowers:*` | hooks/session-start:11-46 |

SameWrite owns exactly: `/samewrite`, phrases `stop samewrite` / `samewrite on|off|status` /
`enable|disable samewrite`, file `samewrite-disabled`, env `SAMEWRITE_*`, hook basenames
`write_noop_guard.py` / `samewrite_mode.py`. The `normal mode` collision between Ponytail and
i-have-adhd is theirs; SameWrite does not add a third claimant (test: `tests/test_samewrite_mode.py`
"abaikan 'normal mode'", plus the live cross-check below).

### Coexistence matrix (master prompt §26) — `tests/test_coexist.py`, 46 assertions (+5 live)

| # | case | result |
|---|---|---|
| 1 | SameWrite only | PASS — install/uninstall round-trips to `{}`; hook command runs via `sh -c` with a space-containing path |
| 2–3 | Ponytail only / i-have-adhd only | PASS — SameWrite absent, nothing touched |
| 4–6, 26 | installed alongside, inactive; pre-populated foreign config | PASS — foreign hooks, statusLine, permissions, custom keys, flags, `~/.config/ponytail` byte-identical after install |
| 7–10 | all combinations active | PASS (files/flags) — one core line, no foreign flag changed, guard still denies identical writes, prompt hook silent on ordinary prompts |
| 11 | different activation orders | PASS — same hook set either order |
| 12 | SameWrite off while others active | PASS — only `samewrite-disabled` appears; guard and SessionStart stand down |
| 13–14 | Ponytail / i-have-adhd off while SameWrite active | PASS — SameWrite unaffected, does not recreate foreign flags |
| 15–19 | session start / resume / clear / compaction / reload | PASS — exactly one core line per SessionStart, none when off |
| 20 | subagent spawn | PASS by design — no SubagentStart hook registered |
| 21–25 | explicit output-only format · long-form explanation · destructive · public-API ambiguity · CRITICAL auth change | **EXPERIMENTAL** — benchmark fixtures `outputonly`, `explainlong`, `apiambig`, `authline` (destructive: no fixture) |
| 27 | existing/custom statusLine; malformed JSON | PASS — preserved on install and uninstall; malformed settings untouched with a warning, rc 1 |
| 28–29 | OpenCode per-turn transform · Pi before-agent injection | **UNSUPPORTED** — no adapter shipped |
| 30 | Windows + POSIX paths | **PARTIAL** — POSIX spaces/`$`/quotes tested; Windows UNTESTED |

Live cross-check (run here with `SAMEWRITE_REF_DIR` pointing at the clones, node 24): the real
`ponytail-mode-tracker.js` ignores `stop samewrite` (`.ponytail-active` survives), `stop ponytail`
really clears it and leaves no `samewrite-disabled`; the real `always-on.mjs` injects with its flag
present and `stop samewrite` leaves that flag alone. 5 assertions, all PASS. CI runs the same
suite without the clones (fixture surfaces only) and prints `SKIP` for the live part.

## 4. Runtime support matrix (master prompt §25)

| host | status | evidence |
|---|---|---|
| Claude Code 2.1.270 | **VERIFIED** for skill listing + on-demand body + hooks | benchmark transcripts (arms D, D2, H, I, J: `treatment_ok`), `tests/test_coexist.py` `sh -c` run |
| Codex / OpenCode (AGENTS.md readers) | INSTRUCTION_ONLY, UNTESTED | `adapters/AGENTS.samewrite.md` generated; no run executed |
| Gemini CLI (GEMINI.md) | INSTRUCTION_ONLY, UNTESTED | `adapters/GEMINI.samewrite.md` generated |
| Pi/OMP, Copilot, Cursor, Hermes | UNSUPPORTED | nothing shipped |

"Installs" is not "works": only Claude Code has a transcript proving the text reached the model.

## 5. Backward compatibility (master prompt §32)

- plugin name `samewrite` unchanged; marketplace entry unchanged except version.
- `skills/edit-discipline/SKILL.md` byte-identical to 1.0.0; it stays listed. The new skill's
  body carries the same fraction rule and names `edit-discipline` as its source, so a user who
  invokes only the old skill sees no change. Deprecation: documented in README; not removed.
- `hooks/install.sh` default behaviour unchanged (guard only). Two edits: hook command is now
  quoted (`printf %q`) so paths with spaces work, and the idempotency check keys on the basename
  `write_noop_guard.py` instead of the exact old command string — a machine holding the 1.0.0
  entry is recognised as already installed rather than getting a second entry.
- `write_noop_guard.py`: one new early-exit (`samewrite-disabled` marker). 64/64 old assertions
  pass; new tests prove deny still fires without the marker (positive control) and stops with it.
- measurement tooling (`tools/*.py`) untouched; `experiments/skill-ab/` untouched; run manifests
  untouched (new runs live in `experiments/vnext/runs/`, classified below).

## 6. Mechanisms evaluated

| mechanism | source | decision | label |
|---|---|---|---|
| whole-message exact off-phrase with trailing-punctuation strip + "add a normal mode toggle" negative test | ponytail hooks/ponytail-config.js:40-43, tests/hooks.test.js:110-126 | **borrowed** (re-implemented, `samewrite_mode.parse`) | MEASURED_BY_SAMEWRITE (deterministic tests) |
| SessionStart matcher `startup\|resume\|clear\|compact` re-inject, fail-silent, frontmatter strip | i-have-adhd hooks/hooks.json:5-11, always-on.mjs:15-44 | **borrowed** for the opt-in core line | MEASURED_BY_SAMEWRITE (tests) / cost EXPERIMENTAL (arm D2) |
| foreign-preserving uninstall (own-basename filter, malformed JSON → warn, untouched) | ponytail scripts/uninstall.js:43-77; caveman bin/lib/settings.js:195-227 | **borrowed** (`hooks/uninstall.sh`) | MEASURED_BY_SAMEWRITE |
| rule-copy drift CI + version pin across manifests | ponytail scripts/check-rule-copies.js, check-versions.js:21-30 | **borrowed** (`tools/adapters.py --check`, `tests/test_adapters.py`) | MEASURED_BY_SAMEWRITE |
| scorer self-test (GOOD→GREEN, BAD→RED) before paid runs | ponytail tests/correctness.test.js:18-35; i-have-adhd tests/test_judge.py | **borrowed** (`experiments/vnext/selftest.py`, 53 checks) | MEASURED_BY_SAMEWRITE |
| failed-fix counter → stop and re-investigate | superpowers skills/systematic-debugging/SKILL.md:191-212 | **borrowed** as instruction (two failed fixes → `ROOT_CAUSE_REASSESSMENT`) | EXPERIMENTAL (fixtures cannot force two failed fixes) |
| revert-fix-must-fail verifier check | superpowers verification-before-completion/SKILL.md:84 | **borrowed** as instruction ("plant a mutation, see RED, restore, see GREEN") | EXPERIMENTAL |
| symbol-first progressive reading; full-file-read stops symbolic re-analysis; batch independent calls | serena system_prompt.yml:12-29, 43-47 | **borrowed** as the ladder wording; explicit deference when a symbol-level tool is loaded | EXPERIMENTAL |
| never-worse guard (filtered only if smaller) + failure-only raw spool with content-hash recall | rtk src/core/guard.rs:17-23, tee.rs:53-57, retriever.rs:83-88 | **not built** — rtk already ships it for Bash; a second PreToolUse(Bash) rewriter would compete, not compose (master prompt §5). Spool (§19) recorded as rejected-for-now: it hides nothing only if it stores everything, and rtk's measured design stores failures only. | REJECTED (this iteration) |
| Read-without-limit → inject `limit` (PreToolUse updatedInput) | token-savior hooks/read_guard_hook.py:109-188 | **not built** — same layer as rtk's rewriter; instruction "read a range, not a file" is measured instead (fixture `hugefile`) | REJECTED (this iteration) |
| repo-map PageRank + token-budget binary search | aider aider/repomap.py:365-575, 667-703 | **not built** — needs tree-sitter + a runtime; out of scope for an instruction plugin | REJECTED |
| edit-format cascade + shared reflection cap (3) | aider editblock_coder.py:157-188, base_coder.py:101 | idea only: the "two failed fixes" cap is the instruction-level analogue | INFERRED |
| per-turn reinforcement injection | caveman caveman-mode-tracker.js:111-125 | **rejected** — repo's own evidence: recurring blocks cost carry without proportionate benefit | REJECTED |
| brevity-word activation (`be brief`, `less tokens`) | caveman caveman-parse.js:137 | **avoided** — SameWrite uses none of those words as triggers, so it cannot trip Caveman | MEASURED_BY_SAMEWRITE (parse tests) |
| memory engine / symbol index / proxy | token-savior, serena, caveman engine | **rejected** — duplicates of claude-mem / serena / rtk; "do not import five versions of the same idea" | REJECTED |

Externally reported numbers seen in the references and **not** adopted as SameWrite claims:
Ponytail "~54% less code · ~20% cheaper" (README.md:33); Caveman "65% output tokens saved"
(README.md:68); rtk "up to 90% of bash output" (README.md:6, scorer = bytes/4); token-savior
"97.9% on tsbench at −80% tokens" (README.md:6, its own README withdraws verifiability at :25-48);
i-have-adhd eval "+0.427 weighted, release gate FAILED" (evals/RESULTS.md:29-38); aider
"pass_rate_2: 77.4" (README.md:100-121); serena "~2x more token-efficient" (docs/04-evaluation,
agent self-assessed). All `EXTERNALLY_REPORTED`.

## 7. Verification actually run

| suite | assertions | what it proves |
|---|---|---|
| `tests/test_write_noop_guard.py` | 64 | guard unchanged; state dir isolated from the real profile |
| `tests/test_profiles.py` | 13 | unchanged |
| `tests/test_plugin_manifest.py` | 23 | both skills have valid front matter, names = directories, versions agree |
| `tests/test_carry.py` | 39 | unchanged |
| `tests/test_skills.py` | 17 | unchanged |
| `tests/test_health.py` | 9 | unchanged |
| `tests/test_samewrite_mode.py` | 55 | parser accepts only own phrases; `normal mode`/`stop ponytail`/… ignored; marker 0600, only file created; guard obeys marker with positive control first; fail-open on bad stdin / unwritable dir; SessionStart core only with `SAMEWRITE_CORE=1` and not when off; version pin |
| `tests/test_adapters.py` | 19 | adapters byte-equal to generator; mutated adapter turns `--check` RED; command surface documented = parsed; `normal mode` appears only as a prohibition; versions agree; description ≤ 400 chars |
| `tests/test_coexist.py` | 46 (+5 live) | matrix above |
| `experiments/vnext/selftest.py` | 53 | every oracle turns RED on its planted bad fixture (one weak neighbour test was caught and fixed by this: `authline`'s symptom patch initially scored ROOT) |

Verify-the-verifier, in words: the guard "off" test first proves deny fires **without** the marker
(it did not on the first draft — the file sat outside `SAMEWRITE_ROOT`, so "allowed when off" was
passing for the wrong reason; fixed by pinning `SAMEWRITE_ROOT`). The adapter drift check is
proven to fail on a mutated copy. The benchmark scorer is proven to distinguish golden from
symptom on every build fixture.

## 8. Benchmark (pre-registered: `experiments/vnext/PREREGISTRATION.md`)

RESULTS_PLACEHOLDER

## 9. Release gate and status

STATUS_PLACEHOLDER

## 10. Files changed

FILES_PLACEHOLDER
