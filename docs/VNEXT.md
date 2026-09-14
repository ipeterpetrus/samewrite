# SameWrite vNext — build report (2026-09-14/15)

**CURRENT state is §12 (hardening + confirmatory run).** §1–§9 are the first build (HISTORICAL:
the mode machinery they describe was removed in §11), §11 the continuation (SUPERSEDED where §12
differs). Everything is measured here, labelled `EXTERNALLY_REPORTED`, or labelled `UNTESTED`.

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

### Coexistence matrix (master prompt §26) — `tests/test_coexist.py`, 49 assertions (+5 live)

| # | case | result |
|---|---|---|
| 1 | SameWrite only | PASS — install/uninstall round-trips to `{}`; hook command runs via `sh -c` with a space-containing path |
| 2–3 | Ponytail only / i-have-adhd only | PASS — SameWrite absent, nothing touched |
| 4–6, 26 | installed alongside, inactive; pre-populated foreign config | PASS — foreign hooks, statusLine, permissions and custom keys **structurally** unchanged after install (the installer re-serialises `settings.json` with `indent=2`, so formatting is not byte-preserved); foreign flag files and `~/.config/ponytail` byte-identical |
| 7–10 | all combinations active | PASS, SameWrite-side only — one core line, no foreign flag changed, guard still denies identical writes, prompt hook silent on ordinary prompts. The foreign hooks themselves run only in the live block below; here their state is constructed |
| 11 | different activation orders | PASS — same hook set either order |
| 12 | SameWrite off while others active | PASS — only `samewrite-disabled` appears; guard and SessionStart stand down |
| 13–14 | Ponytail / i-have-adhd off while SameWrite active | PASS — the test removes the foreign flag; SameWrite unaffected, does not recreate it |
| 15–19 | session start / resume / clear / compaction / reload | PASS for SameWrite's own hook — exactly one core line per SessionStart, none when off; the hook does not consult `source`, so these five rows are one behaviour, not five |
| 20 | subagent spawn | PASS by construction — no SubagentStart entry is registered; no subagent was exercised |
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
| scorer self-test (GOOD→GREEN, BAD→RED) before paid runs | ponytail tests/correctness.test.js:18-35; i-have-adhd tests/test_judge.py | **borrowed** (`experiments/vnext/selftest.py`, 68 checks) | MEASURED_BY_SAMEWRITE |
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
| `tests/test_samewrite_mode.py` | 57 | parser accepts only own phrases; `normal mode`/`stop ponytail`/… ignored; marker 0600, only file created; guard obeys marker with positive control first; fail-open on bad stdin / unwritable dir; SessionStart core only with `SAMEWRITE_CORE=1` and not when off; version pin |
| `tests/test_adapters.py` | 19 | adapters byte-equal to generator; mutated adapter turns `--check` RED; command surface documented = parsed; `normal mode` appears only as a prohibition; versions agree; description ≤ 400 chars |
| `tests/test_coexist.py` | 49 (+5 live) | matrix above; plus: same-basename foreign hook in another directory survives uninstall, a foreign command merely containing the substring does not suppress install, marker under `SAMEWRITE_STATE_DIR` is removed on uninstall |
| `experiments/vnext/selftest.py` | 68 | every oracle turns RED on its planted bad fixture (one weak neighbour test was caught and fixed by this: `authline`'s symptom patch initially scored ROOT) |

Verify-the-verifier, in words: the guard "off" test first proves deny fires **without** the marker
(it did not on the first draft — the file sat outside `SAMEWRITE_ROOT`, so "allowed when off" was
passing for the wrong reason; fixed by pinning `SAMEWRITE_ROOT`). The adapter drift check is
proven to fail on a mutated copy. The benchmark scorer is proven to distinguish golden from
symptom on every build fixture.

## 8. Benchmark (pre-registered: `experiments/vnext/PREREGISTRATION.md`)

Run 2026-09-14, `experiments/vnext/runs/pilot1.rescored.jsonl` (manifest: `runs/manifest.json`).
110 runs · 11 arms × 10 fixtures × 1 repeat · `claude-haiku-4-5-20251001` · CLI 2.1.270 · 0 rows
excluded (every run rc 0, transcript found, `treatment_ok` true — the expected banner/listing
present and no foreign banner in any of the 110 transcripts).

Two scorer defects were found **by the pilot itself** and fixed before analysis, with the runs
re-scored from the preserved working directories (`rescore.py`; original verdicts kept per row):
`.pytest_cache` created by the agent's own test run counted as "a file added" (3 correct "no fix
needed" answers scored SYMPTOM), and the output-only oracle accepted one argument order of a
correct `clamp` (`min(hi, max(x, lo))` scored FAIL). Both now have self-test cases; the cross-family review below added three more oracle holes (added files such as a test-skipping `conftest.py`, a bare `?` counting as a question, added files under "do not edit") — all covered now (68 checks). Re-scoring after every fix left all 110 verdicts as reported here.

Per arm (weighted context = input + 1.25·cache_creation + 0.1·cache_read, mean over the arm's 10
runs; listing B = bytes of the skill listing the CLI injects, a per-turn always-on cost):

| arm | ROOT/n | weighted ctx | output tok | turns | Read B | Bash B | listing B | verdicts |
|---|---|---|---|---|---|---|---|---|
| A | 10/10 | 60,887 | 2,646 | 11.3 | 2,098 | 1,448 | 6,183 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| B | 10/10 | 56,779 | 2,378 | 11.8 | 1,492 | 1,650 | 6,183 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| C | 10/10 | 64,212 | 2,803 | 11.9 | 1,449 | 2,899 | 6,434 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| D | 10/10 | 66,158 | 2,918 | 12.2 | 2,126 | 1,894 | 6,562 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| E | 10/10 | 63,038 | 2,671 | 10.2 | 2,099 | 1,279 | 6,183 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| F | 10/10 | 61,680 | 2,540 | 10.8 | 2,083 | 1,630 | 6,183 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| G | 10/10 | 70,290 | 2,757 | 11.6 | 2,114 | 1,569 | 6,183 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| H | 10/10 | 67,316 | 2,742 | 12.7 | 2,145 | 1,937 | 6,562 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| I | 10/10 | 63,240 | 2,741 | 11.2 | 1,476 | 1,463 | 6,562 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| J | 10/10 | 66,882 | 2,483 | 11.2 | 2,143 | 1,712 | 6,562 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |
| D2 | 10/10 | 63,576 | 2,961 | 12.2 | 1,550 | 1,391 | 6,562 | alread=ROOT apiamb=ROOT authli=ROOT explai=ROOT hidden=ROOT hugefi=ROOT noisyl=ROOT onelin=ROOT output=ROOT sympto=ROOT |

Pre-registered contrasts, paired by fixture (two-sided exact sign test on "cheaper"):

```
  D vs C (H1 candidate vs current): n=10 ROOT 10 vs 10; both-ROOT 10: D cheaper in 4/10 (sign p=0.754), median Δweighted +1.4%
   D dearer on: alreadycorrect, apiambig, authline, hugefile, oneline, symptomtrap
D vs A (vs bare): n=10 ROOT 10 vs 10; both-ROOT 10: D cheaper in 3/10 (sign p=0.344), median Δweighted +1.5%
   D dearer on: alreadycorrect, apiambig, hugefile, noisylog, oneline, outputonly, symptomtrap
D vs B (vs one sentence): n=10 ROOT 10 vs 10; both-ROOT 10: D cheaper in 2/10 (sign p=0.109), median Δweighted +22.4%
   D dearer on: apiambig, authline, explainlong, hiddencaller, hugefile, noisylog, oneline, symptomtrap
D2 vs D (H4 hooks tax): n=10 ROOT 10 vs 10; both-ROOT 10: D2 cheaper in 4/10 (sign p=0.754), median Δweighted +0.7%
   D2 dearer on: explainlong, hiddencaller, hugefile, noisylog, oneline, outputonly
H vs E (H2/H3 +vNext on ponytail): n=10 ROOT 10 vs 10; both-ROOT 10: H cheaper in 4/10 (sign p=0.754), median Δweighted +1.8%
   H dearer on: alreadycorrect, apiambig, hiddencaller, oneline, outputonly, symptomtrap
I vs F (H2/H3 +vNext on i-have-adhd): n=10 ROOT 10 vs 10; both-ROOT 10: I cheaper in 4/10 (sign p=0.754), median Δweighted +13.6%
   I dearer on: alreadycorrect, explainlong, hiddencaller, oneline, outputonly, symptomtrap
J vs G (H2/H3 +vNext on both): n=10 ROOT 10 vs 10; both-ROOT 10: J cheaper in 6/10 (sign p=0.754), median Δweighted -3.5%
   J dearer on: authline, hiddencaller, hugefile, outputonly
```

**Reading.** Every arm reached the ceiling — 10/10 ROOT, including the bare agent — so the
fixtures cannot separate the arms on correctness; this is the same ceiling `experiments/skill-ab`
hit in its rounds 1–2, on a stronger model than expected for these tasks. On cost, the candidate
D is **not** cheaper than current SameWrite (4/10, median +1.4%), not cheaper than the bare agent
(3/10, +1.5%) and dearer than the one-sentence prefix on 8 of 10 fixtures (median +22.4%,
p = 0.109). Its always-on cost is visible and small: the listing entry adds 379 bytes per turn
over the bare agent (C adds 251). Coexistence held: adding D to Ponytail, i-have-adhd or both
lost no correctness (10/10 everywhere) and moved cost inside noise in both directions (4/10, 4/10,
6/10 cheaper). The hooks arm D2 was not measurably dearer than D (+0.7% median), so the
"persistence tax" question is also unresolved at this n.

Losing cases, by name: D dearer than C on `alreadycorrect`, `apiambig`, `authline`, `hugefile`,
`oneline`, `symptomtrap`; dearer than B on everything except `alreadycorrect` and `outputonly`.

What this does **not** show: any effect at all, in either direction, at a size this pilot could
detect (n = 10, ceiling on correctness). It shows the instruments work, the treatment lands, and
the candidate's cost is in the same band as the current skill's.

## 9. Release gate and status

**NOT_PROVEN.**

Gate items from master prompt §36, as they stand on this evidence:

| gate | result |
|---|---|
| no CRITICAL / material correctness or safety regression | PASS — 10/10 in every arm, `authline` (CRITICAL class) ROOT everywhere |
| no new needless-clarification habit | PASS — `apiambig` asked in every arm, no other fixture ended in a question |
| repair cascades not worse | not measurable — no fixture produced a failed fix in any arm |
| coexistence tests pass | PASS — 46 deterministic + 5 live assertions |
| SameWrite never responds to generic `normal mode` | PASS — parser tests + live cross-check |
| foreign plugin state/config untouched | PASS — byte-hash snapshots before/after every operation |
| benchmark conditions comparable | PASS with one caveat — config isolated per **arm**, not per run: concurrent runs in an arm shared it, and Ponytail's hook writes `.ponytail-statusline-nudged` once, so the first run in each Ponytail arm (E, G, H, J) received its one-time status-line nudge text and the others did not. Pinned model/CLI/flags, 0 excluded rows. `rig.py` now builds one config per run |
| instruments self-test | PASS — 58 checks; two false-RED defects found by the pilot and fixed before analysis |
| instruction overhead measured | PASS — +379 B/turn listing (D) vs +251 B (C) vs 0 (A); D2 SessionStart line ≈ 250 B |
| results include losing cases | PASS — listed by name above |
| licenses / provenance | PASS — nine pins, no code copied, Apache-2.0 sources idea-only |
| exact diff contains no unrelated mutation | PASS — `edit-discipline`, `tools/*.py`, `experiments/skill-ab/` untouched |
| **candidate beats current SameWrite on its objective** | **FAIL** — D vs C: same correctness, cheaper in 4/10, median +1.4% |

Because the last row fails, the runtime candidate is **not promoted**: `samewrite` ships in the
working tree as an on-demand skill next to `edit-discipline`, labelled experimental, with its
hooks opt-in and off by default. Nothing here is pushed, tagged or released. A confirmatory run
that could change this verdict needs ≥ 16 fresh fixtures hard enough to leave the ceiling (a
smaller model, or tasks with a real hidden-caller / two-failed-fix structure), and would be
pre-registered separately.

### Cross-family review (codex lane, `codex_review.sh`, diff `0aec7ce..f04ba44`, code paths)

Verdict returned: NEEDS-FIX, 5 HIGH / 9 MED. Disposition:

| finding | disposition |
|---|---|
| HIGH `samewrite_mode.py`: `makedirs` follows a symlinked parent before creating the marker | **fixed** — the state directory is never created; missing → notice, no write. Marker itself stays `O_NOFOLLOW`. Test added |
| HIGH `uninstall.sh`: ownership by basename would delete a foreign hook named `write_noop_guard.py` elsewhere | **fixed** — ownership = the exact installed path token (`shlex.split`), same in `install.sh`'s idempotency check. Test added |
| HIGH `rig.py`: added files ignored → a `conftest.py` skipping all tests could score ROOT | **fixed** — any unexpected added file → INVALID (build) / FAIL (text). Self-test added. No pilot row had an added file |
| HIGH `rig.py`: a custom credential filename was not cleaned up | **fixed** — the copy always lands under the CLI's fixed name and every copy is tracked and removed in `finally` |
| HIGH `rig.py`: one config dir per arm shared by parallel runs | **fixed for future runs** (one directory per run); pilot caveat recorded above |
| MED `install.sh`: foreign command containing the substring suppresses install | **fixed** with the exact-path check; test added |
| MED `install.sh`: `printf %q` emits bash-only `$'…'` for newlines | **fixed** — POSIX single-quote escaping |
| MED `uninstall.sh`: marker removed only from `CLAUDE_CONFIG_DIR` | **fixed** — same resolver as the hooks; test added |
| MED `analyze.py`: repeats overwrite each other; ties counted as "dearer" | **fixed** — pairs keyed by (fixture, rep); ties dropped from the sign test |
| MED `rig.py`: `must_ask` satisfied by any `?` | **fixed** — question must ask for the name (`ask_re`); self-test with `No rename was made. Why?` → FAIL |
| MED `test_coexist.py`: several rows asserted by construction | **accepted, relabelled** in the matrix above; the live block is the only place foreign hooks execute |
| MED `docs/VNEXT.md`: "byte-identical after install" is false (JSON re-serialised) | **accepted, reworded** to structural preservation |
| MED `docs/VNEXT.md`: "isolated config per arm" overstated | **accepted, caveat added** to the gate table |

Nothing in the review changed a pilot verdict: rescoring after every oracle fix reproduced the
same 110 results (0 excluded, all arms 10/10).

## 10. Files changed

Against `0aec7ce` (`git diff --stat`, after the continuation in §11; pushed as `release/vnext-1.1.0`, PR #2):

```
.claude-plugin/marketplace.json                |   2 +-
 .claude-plugin/plugin.json                     |   2 +-
 .github/workflows/test.yml                     |  10 +-
 .gitignore                                     |   4 +
 README.md                                      | 699 +++++++++++----------------------------------
 adapters/AGENTS.samewrite.md                   |  62 ++++
 adapters/GEMINI.samewrite.md                   |  62 ++++
 docs/VNEXT.md                                  | 444 ++++++++++++++++++++++++++++
 docs/reference-audits/aider.md                 |  44 +++
 docs/reference-audits/caveman.md               |  48 ++++
 docs/reference-audits/i-have-adhd.md           |  46 +++
 docs/reference-audits/ponytail.md              |  54 ++++
 docs/reference-audits/rtk.md                   |  49 ++++
 docs/reference-audits/serena.md                |  57 ++++
 docs/reference-audits/superpowers.md           |  55 ++++
 docs/reference-audits/token-savior.md          |  41 +++
 experiments/presentation/PREREGISTRATION.md    |  63 ++++
 experiments/presentation/analyze_pres.py       |  62 ++++
 experiments/presentation/fixtures_pres.py      | 196 +++++++++++++
 experiments/presentation/rig_pres.py           | 219 ++++++++++++++
 experiments/presentation/runs/manifest.json    |  40 +++
 experiments/presentation/runs/pres1.jsonl      |  64 +++++
 experiments/presentation/runs/smoke.jsonl      |   4 +
 experiments/presentation/selftest_pres.py      | 107 +++++++
 experiments/presentation/skill_before/SKILL.md |  60 ++++
 experiments/vnext/PREREGISTRATION.md           |  85 ++++++
 experiments/vnext/README.md                    |  23 ++
 experiments/vnext/analyze.py                   |  89 ++++++
 experiments/vnext/fixtures.py                  | 325 +++++++++++++++++++++
 experiments/vnext/rescore.py                   |  22 ++
 experiments/vnext/rig.py                       | 270 +++++++++++++++++
 experiments/vnext/runs/manifest.json           |  58 ++++
 experiments/vnext/runs/pilot1.jsonl            | 110 +++++++
 experiments/vnext/runs/pilot1.rescored.jsonl   | 110 +++++++
 experiments/vnext/runs/smoke.jsonl             |   4 +
 experiments/vnext/selftest.py                  | 133 +++++++++
 hooks/install.sh                               |  39 ++-
 hooks/uninstall.sh                             |  51 ++++
 skills/edit-discipline/SKILL.md                |  62 +---
 skills/samewrite/SKILL.md                      |  66 +++++
 tests/test_adapters.py                         |  87 ++++++
 tests/test_coexist.py                          | 311 ++++++++++++++++++++
 tools/adapters.py                              |  61 ++++
 43 files changed, 3808 insertions(+), 592 deletions(-)
```

Untouched on purpose: every `tools/*.py` except the new `adapters.py`, `experiments/skill-ab/`, `docs/FINDINGS.md`, `docs/FIELD_DATA.md`, `LICENSE`.

## 11. Continuation: human-first output, one runtime (2026-09-14, same day)

Supersedes §1, §3 and §9 where they differ. Two directives arrived after the pilot: make the
default human-facing output action-first without a second plugin, and keep ONE SameWrite.

**Fact that reshaped the design.** In pilot1 the skill *body* was invoked in **0 of 50**
samewrite-arm runs and `edit-discipline` in 0 of 10 (`tool_counts` has no `Skill` call in any
of the 110 transcripts). Under `claude -p` only the always-on listing description reaches the
model; the body reaches it only when invoked. So the earlier arm D measured the description, not
the body, and any output policy that lives only in the body would be measured as nothing.

**Delta (surgical):**

| change | why |
|---|---|
| `skills/samewrite/SKILL.md`: new **Output** section replaces "Presentation and controls"; description gains the clause "answer result-first with only what a human needs to act or verify" | the compact human-output policy (§4 of the directive), in the one channel that is always on and in the body for invoked use |
| `skills/edit-discipline/SKILL.md` → 755-byte compatibility alias with `disable-model-invocation: true` | one runtime (§16): the policy text exists once; `/edit-discipline` still works for 1.0.0 installs; zero listing bytes per turn (verified in every presentation transcript: `- edit-discipline:` absent from the listing) |
| **removed** `hooks/samewrite_mode.py`, its 57 tests, the `SAMEWRITE_MODE_HOOK` install path, the `samewrite-disabled` marker in the guard | §15 (no mode machinery merely because Ponytail/i-have-adhd have it) plus pilot1 measurement: arm D2 (hooks) was not more correct and +0.7% dearer than D. `write_noop_guard.py` and its 64 tests are byte-identical to 1.0.0 again |
| `hooks/install.sh` / `uninstall.sh` keep the review fixes (POSIX quoting, exact-path ownership) | unchanged behaviour, smaller surface |
| `tests/test_coexist.py` rewritten for a hook-free skill; `tests/test_adapters.py` checks the alias and that each policy section exists exactly once | the matrix now says N/A where there is nothing to re-inject instead of testing a hook that no longer exists |
| `experiments/presentation/` — 8 adversarial cases (§8 of the directive), 8 arms, self-tested prose classifiers, pre-registration, per-run isolated configs, multi-turn via `--continue` | the presentation benchmark (§7) |

Runtime instruction size, before → after (bytes): listing description 330 → 366 (always on);
body 4,011 → 4,753 (on demand); `edit-discipline` listing entry ~250 → 0 (hidden); hooks
injected per session 0 → 0. Net always-on change: **+36 bytes** for the output clause and
**−~250** for the retired alias entry.

### Presentation pilot (`experiments/presentation/runs/pres1.jsonl`, pre-registered)

| arm | ROOT | human_ok | out tok (mean) | last-turn out tok | injected B | pre/clo/decor | state lines | words (mean) |
|---|---|---|---|---|---|---|---|---|
| A | 7/8 | 5/8 | 3,140 | 2,654 | 6,388 | 0/1/0 | 0 | 83 |
| B | 7/8 | 6/8 | 3,022 | 2,528 | 6,774 | 0/0/0 | 0 | 66 |
| C | 7/8 | 4/8 | 2,844 | 2,406 | 13,672 | 0/1/0 | 0 | 71 |
| D | 7/8 | 5/8 | 2,894 | 2,384 | 6,799 | 0/1/0 | 0 | 77 |
| Dh | 7/8 | 7/8 | 2,972 | 2,432 | 6,962 | 0/0/0 | 0 | 64 |
| Dm | 7/8 | 5/8 | 3,252 | 2,708 | 6,916 | 0/1/0 | 0 | 73 |
| E | 7/8 | 5/8 | 2,804 | 2,410 | 13,416 | 0/0/0 | 0 | 63 |
| F | 7/8 | 5/8 | 2,908 | 2,488 | 14,081 | 0/1/0 | 0 | 57 |

Per fixture (verdict / human_ok):

```
  blocker          A=INVA/NO  B=INVA/NO  C=INVA/NO  D=INVA/NO  Dh=INVA/NO  Dm=INVA/NO  E=INVA/NO  F=INVA/NO
  edit_simple      A=ROOT/ok  B=ROOT/ok  C=ROOT/ok  D=ROOT/ok  Dh=ROOT/ok  Dm=ROOT/ok  E=ROOT/ok  F=ROOT/ok
  explain_detail   A=ROOT/ok  B=ROOT/ok  C=ROOT/ok  D=ROOT/ok  Dh=ROOT/ok  Dm=ROOT/ok  E=ROOT/ok  F=ROOT/ok
  multistage       A=ROOT/NO  B=ROOT/ok  C=ROOT/NO  D=ROOT/NO  Dh=ROOT/ok  Dm=ROOT/NO  E=ROOT/ok  F=ROOT/NO
  nothing_changed  A=ROOT/ok  B=ROOT/ok  C=ROOT/ok  D=ROOT/ok  Dh=ROOT/ok  Dm=ROOT/ok  E=ROOT/ok  F=ROOT/ok
  output_only      A=ROOT/ok  B=ROOT/ok  C=ROOT/ok  D=ROOT/ok  Dh=ROOT/ok  Dm=ROOT/ok  E=ROOT/ok  F=ROOT/ok
  security         A=ROOT/ok  B=ROOT/ok  C=ROOT/NO  D=ROOT/ok  Dh=ROOT/ok  Dm=ROOT/ok  E=ROOT/NO  F=ROOT/ok
  user_must_run    A=ROOT/NO  B=ROOT/NO  C=ROOT/NO  D=ROOT/NO  Dh=ROOT/ok  Dm=ROOT/NO  E=ROOT/NO  F=ROOT/NO
```

Pre-registered contrasts:

```
  D vs B (H1 now vs before): n=8 ROOT 7 vs 7 · human_ok 5 vs 6 · D fewer output tokens in 5/8
     human_ok LOST by D: multistage
  D vs A (vs bare): n=8 ROOT 7 vs 7 · human_ok 5 vs 5 · D fewer output tokens in 5/8
  D vs C (H2 vs i-have-adhd full): n=8 ROOT 7 vs 7 · human_ok 5 vs 4 · D fewer output tokens in 4/8
  Dh vs D (H5 one-liner P2): n=8 ROOT 7 vs 7 · human_ok 7 vs 5 · Dh fewer output tokens in 3/8
  Dm vs D (H5 one-liner P1): n=8 ROOT 7 vs 7 · human_ok 5 vs 5 · Dm fewer output tokens in 3/8
  E vs D (H4 +ponytail): n=8 ROOT 7 vs 7 · human_ok 5 vs 5 · E fewer output tokens in 5/8
     human_ok LOST by E: security
  F vs D (H4 +i-have-adhd): n=8 ROOT 7 vs 7 · human_ok 5 vs 5 · F fewer output tokens in 5/8
  F vs C (stacked vs adhd alone): n=8 ROOT 7 vs 7 · human_ok 5 vs 4 · F fewer output tokens in 4/8
```

**Reading.** Correctness is flat: 7/8 in every arm, and the one miss is the same everywhere —
on `blocker` (two contradictory tests) the model *edited the test* in all 8 arms, so no
instruction here changed that behaviour (INVALID, counted as a failure). `human_ok` — the
per-case contract (result first, numbered human actions, full detail on request, security
evidence, no manufactured status, no filler) — was 6/8 for SameWrite before this change (B),
5/8 for the new description alone (D: it lost `multistage`, whose final "ok" turn ended in
"Let me know if you need anything else!"), 4/8 for the full i-have-adhd hook at 2× the injected
bytes, and **7/8 for D plus the one-sentence SessionStart injection (Dh)** — the only arm that
produced numbered human actions on `user_must_run` and a filler-free final turn. The micro
variant (Dm, P1) gained nothing over D. Output tokens: D fewer than B on 5/8, means within 5%
of each other in every arm; the hook costs +163 bytes per session start. Stacking: with
Ponytail (E) correctness held and `human_ok` stayed 5/8, but `security` lost its evidence
sentence to Ponytail's "at most three short lines" — a shortening interaction, not a
contradiction; with i-have-adhd (F) 5/8, no doubled status text. The skill body was again
invoked 0 times in 64 runs — under `claude -p` the listing description and the SessionStart
line are the only channels that reached the model.

Pre-registered rules: H1 (D ≥ B on human_ok) **fails by one fixture**; H2 (D ≈ C) holds
(5 vs 4 at half the carry); H3 holds (`explain_detail` ROOT with ≥120 words in D, Dh, Dm);
H4 holds (no correctness loss with Ponytail or i-have-adhd); H5's threshold (one-liner raises
human_ok by ≥ 2) is met exactly by P2 (7 vs 5), so the P2 sentence ships as an **opt-in**
`SAMEWRITE_OUTPUT_HOOK=1` install option, default off, and the same sentence is the first
sentence of the skill's Output section (one canonical text; drift-tested). n = 8, one repeat:
direction and instrument validation, not significance.

### Continuation gate

| gate (continuation §19) | result |
|---|---|
| behaviour: action-first, scannable, concise, concrete errors, not repetitive, detailed on request | **NOT_PROVEN** for the description alone (5/8 vs 6/8 before); 7/8 with the opt-in one-liner; `explain_detail` and `output_only` ROOT everywhere |
| token economy: no unjustified persistent overhead | PASS — +36 B always-on for the output clause, −~250 B for the hidden alias, +163 B per session start only when the hook is opted in |
| correctness | PASS — 7/8 in every arm, identical miss everywhere |
| completeness on requested detail | PASS — `explain_detail` ≥ 120 words, all facts, in D/Dh/Dm |
| coexistence Ponytail / i-have-adhd / both | PASS on correctness; one shortening interaction with Ponytail on the security fixture, recorded |
| no `normal mode` claim | PASS — skill text, tests, README |
| one canonical runtime | PASS — `edit-discipline` is a hidden 755-byte alias; policy sections exist exactly once |

Verdict for this continuation: **NOT_PROVEN** (human-output gain not shown for the zero-hook
default at n = 8; shown as direction only for the opt-in one-liner). Everything shipped is
labelled accordingly.

## 12. Hardening + proof pass (2026-09-15) — CURRENT

### 12.1 Remote CI was red: root cause and fix

GitHub Actions on `cc1057e` failed both matrix lanes in `experiments/vnext/selftest.py` with
`56 PASS / 12 FAIL` — every build fixture's golden (expected ROOT) and symptom (expected SYMPTOM)
came back `FAIL`. Reproduced exactly in a clean venv (`python -m venv --without-pip`) and in
`python:3.9-slim` / `python:3.12-slim` containers: **`pytest` is not preinstalled on the runner**,
`python -m pytest` exits 1 with `No module named pytest`, and the rig folded that return code into
a model `FAIL`. The developer machine had pytest, so "local CI-equivalent passed" was an
environment artefact, not evidence.

Fix (commit `786928e`): `requirements-test.txt` (`pytest>=7.4,<9` — 9.x requires Python 3.10, the
matrix keeps 3.9) installed explicitly in the workflow; `fail-fast: false`; `run_pytest()` /
`classify_pytest()` return one of three states (passed, failed, infrastructure) with the pytest
output saved beside the run; `verdict()` emits **`INFRA_ERROR`** for a missing runner, usage or
internal error, zero tests collected, all tests skipped, CLI failure or timeout; `metrics()` marks
empty, truncated or usage-less transcripts `transcript_ok=false`. `analyze*.py` exclude and count
those rows; they never enter a correctness or human_ok tally. Self-tests: 86 (vnext) + 38
(presentation) + 75 (confirmatory), including missing runner → INFRA_ERROR, model syntax error →
FAIL, test-file syntax error → INVALID, stale `.pyc` → still ROOT, empty / truncated / usage-less
transcript, foreign-banner contamination. The container run found a second sensitivity: tests
hardcoded `/usr/bin/python3` (absent in `python:*-slim`); they now use `sys.executable`.

Result: clean `python:3.9-slim` (3.9.25) and `python:3.12-slim` (3.12.14) containers, repository mounted read-only, `pip install -r requirements-test.txt` only — every suite, all three instrument self-tests, the adapter drift check, the README assertion count, the synthetic end-to-end run and the redaction check pass (`CI_LOCAL_OK`). GitHub Actions on `786928e`: both lanes green on the push run (34877517231) and on the pull-request run (34877521771), i.e. on the PR's synthetic merge commit as well as the branch head.

### 12.2 Skill-body activation (§16)

Probe (`experiments/presentation/activation_probe.py`, `runs/probe1.jsonl`, 6 runs, arm D, haiku-4-5,
`claude -p`): the body reached the model in **0/2** runs of an ordinary fix prompt, **1/2** when the
prompt named the skill ("Follow the samewrite skill"), and **2/2** when the prompt started with
`/samewrite` — in that case Claude Code expands the skill into the user message
(`<command-name>/samewrite</command-name>` + the body) without a `Skill` tool call, which is why
the earlier "0 Skill tool calls in 174 runs" count could not see it. All 6 runs fixed the bug
except one implicit run; the `/samewrite` runs cost the most output tokens (3,266 / 4,356 vs
2,639–3,439), consistent with a 4.7 kB body being read and followed.

Answers: (1) yes — a Claude Code skill body is loaded only when the model calls the `Skill` tool
or the user types `/samewrite`; the listing description is the always-on channel; (2) see the probe;
(3) no — SameWrite's measured savings (no-op writes, the edit rule, tool-output economy, the
terseness sentence) come from the guard hook and from short always-on text, not from the body;
(4) yes — the guard is deterministic and the one-sentence SessionStart line is ~170 bytes;
(5) the listing description (0 extra bytes) and the SessionStart line (one small injection per
session); nothing here expands per-turn context.

### 12.3 Evidence-driven optimization loop (§17–§20) — what exists, no new runtime

| stage | mechanism (existing) | privacy | runtime cost |
|---|---|---|---|
| measure aggregates | Claude Code transcripts + `hooks/write_noop_guard.py` ledger (`SAMEWRITE_LEDGER`: event, bytes, blocks, changed fraction, hashed host) | ledger holds no path, filename or content (tested: `tests/test_write_noop_guard.py` "ledger TIDAK memuat path") | one stat + one read per `Write` |
| append privacy-safe evidence | `tools/carry.py --history PATH` (shares and counts per run) | no paths, no content (tested: `tests/test_carry.py`); `extract.py` redacts by default (CI "redaction holds") | offline |
| periodic analysis | `carry.py --history` trend / slope / z-score; `tools/report.py`; `tools/health.py`; `tools/skills.py` | aggregates only | offline |
| candidate optimization | a policy change written as text (skill) or code (hook) | — | — |
| A/B or regression proof | `experiments/vnext`, `experiments/presentation` rigs with self-tested oracles and pre-registration | isolated configs, credential copy deleted after the run | paid runs, offline |
| human-reviewed promotion | pull request; nothing promotes itself | — | — |

No runtime component reads history into the model context; nothing rewrites the skill. The
phrase this repo may use is "evidence-driven optimization loop", not "self-learning".

### 12.4 Confirmatory presentation run (§9–§13) — pre-registered, fresh fixtures

Design frozen at `786928e` (PREREGISTRATION_confirm.md); run 2026-09-14/15 UTC; 256 runs, **0 excluded**
(no INFRA_ERROR, no treatment failure, no CLI failure). Provenance: the first rig invocation recorded
71 rows live, then its recording loop died on a worker exception (the agent deleted fixture files on
`c10_destructive`, `diff_loc()` raised) while the pool kept running; 121 completed runs were re-scored
from their preserved working directories and transcripts (`reconstruct.py`), 4 runs killed mid-flight
were discarded and re-run, and the last 60 jobs ran under `--resume` with the hardened rig. No oracle,
threshold or arm changed between the freeze and the analysis (manifest: `runs/manifest.json`).

| arm | valid | ROOT | human_ok | cost (mean) | out tok | injected B | turns | tool calls | pre/clo/decor | state |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 32/32 | 26 | 23 | 81,470 | 3,133 | 6,389 | 14.1 | 5.1 | 0/4/1 | 0 |
| B | 32/32 | 25 | 22 | 80,872 | 3,136 | 6,774 | 13.8 | 4.8 | 0/1/0 | 0 |
| C | 32/32 | 26 | 23 | 80,176 | 2,895 | 13,676 | 13.2 | 5.1 | 0/0/0 | 1 |
| D | 32/32 | 26 | 23 | 81,166 | 3,242 | 6,799 | 13.7 | 4.9 | 0/1/1 | 0 |
| Dh | 32/32 | 25 | 24 | 83,286 | 3,249 | 6,964 | 14.8 | 5.4 | 0/1/0 | 0 |
| Eh | 32/32 | 24 | 23 | 91,799 | 3,564 | 13,247 | 14.5 | 5.5 | 0/0/0 | 0 |
| Fh | 32/32 | 26 | 24 | 84,889 | 3,330 | 14,252 | 13.1 | 5.2 | 0/0/0 | 0 |
| Gh | 32/32 | 26 | 23 | 89,235 | 3,110 | 20,536 | 13.2 | 5.1 | 0/0/0 | 0 |

Per fixture — ROOT count over 2 reps / human_ok count (arm order A B C D Dh Eh Fh Gh):

```
  c01_trivial_edit            2/2   2/2   2/2   2/2   2/2   2/2   2/2   2/2
  c02_noop                    2/2   2/0   2/0   2/1   2/2   2/2   2/2   2/0
  c03_one_command             0/0   0/0   0/0   0/0   0/0   0/0   0/0   0/0
  c04_multi_commands          2/2   2/2   2/2   2/2   2/2   2/2   2/2   2/2
  c05_blocker                 0/0   0/0   0/0   0/0   0/0   0/0   0/0   0/0
  c06_ambiguous               2/1   2/2   2/2   2/2   2/2   2/2   2/2   2/2
  c07_output_only             2/2   2/2   2/2   2/2   2/2   2/2   2/2   2/2
  c08_explain                 2/2   2/2   2/2   2/2   2/2   2/2   2/2   2/2
  c09_security                2/2   2/2   2/2   2/2   2/2   2/1   2/2   2/2
  c10_destructive             2/2   1/1   2/2   2/2   2/2   2/2   2/2   2/2
  c11_api_compat              0/0   0/0   0/0   0/0   0/0   0/0   0/0   0/0
  c12_multistage              2/0   2/1   2/2   2/1   2/2   2/2   2/2   2/2
  c13_failed_verification     2/2   2/2   2/1   2/2   1/1   1/1   2/1   2/1
  c14_root_cause              2/2   2/2   2/2   2/2   2/2   2/2   2/2   2/2
  c15_terse_with_evidence     2/2   2/2   2/2   2/1   2/1   1/1   2/1   2/2
  c16_no_next                 2/2   2/2   2/2   2/2   2/2   2/2   2/2   2/2
```

Promotion gate, exactly as pre-registered (Dh = D + P2 one-liner vs D = zero-hook default):

```
  CORRECTNESS_NON_INFERIOR=YES
  SAFETY_NON_INFERIOR=YES
  DETAIL_COMPLETENESS=PASS
  HUMAN_OUTPUT_IMPROVEMENT=NOT_PROVEN
  _human={'n': 32, 'dh': 24, 'd': 23, 'wins': 2, 'losses': 1, 'p': 1.0}
  TOTAL_TASK_COST_REGRESSION=NO_MATERIAL_REGRESSION
  _cost={'median_delta': 0.017, 'dearer': 18, 'cheaper': 14, 'p': 0.5966}
  COEXISTENCE=PASS
  _coexistence={'Eh': 'PASS', 'Fh': 'PASS', 'Gh': 'PASS'}
  PROMOTE_P2=NO
```

**Reading.** Correctness is flat and non-inferior everywhere (25–26 of 32 per arm; D 26, Dh 25).
The human-output contract: D 23/32, Dh 24/32 — discordant pairs 2 wins, 1 loss, sign p = 1.0, margin
+1 of the required +4. **HUMAN_OUTPUT_IMPROVEMENT = NOT_PROVEN; PROMOTE_P2 = NO.** The pilot's 7/8 vs 5/8
did not replicate on fresh cases. Cost: Dh median +1.7% (18 dearer / 14 cheaper, p = 0.60) — no
material regression, but no saving either. Coexistence held (Eh, Fh, Gh each within the gate; no
correctness loss, no doubled status text). Three fixtures were floors in every arm and separate nothing:
`c03` (all arms wrote `os.getenv("DB_URL", default)`, and the hidden neighbour expects an empty variable
to fall back — a stricter reading than any arm took), `c05` (13/16 runs created the missing file locally
and rewrote the loader, 3 failed — no arm reported the blocker), `c11` (all arms renamed the public
parameter without a compatibility alias). Six fixtures were ceilings (c01, c04, c07, c08, c14, c16).
Where arms did differ: `c02_noop` (B and Gh 0/2 vs D 1/2, Dh 2/2 — the no-change answer picked up a
closer or a status line), `c12_multistage` (A 0/2, B/D 1/2, Dh 2/2), `c13`/`c15` (Dh and the stacked arms
lost one run each on the evidence sentence).

Skill-body activation in these 256 runs: 0 `Skill` tool calls (as in every `claude -p` run so far).

### 12.5 Final gate

Per hardening §27, `READY_TO_MERGE` requires `HUMAN_OUTPUT=PROVEN`. It is not.

| gate | result |
|---|---|
| LOCAL_FULL_SUITE / PYTHON_3_9 / PYTHON_3_12 / REMOTE_GITHUB_ACTIONS | PASS (219 assertions; clean 3.9 and 3.12 containers; Actions green on push and PR runs) |
| CORRECTNESS / SAFETY | PASS — non-inferior on fresh fixtures; security and destructive cases held |
| HUMAN_OUTPUT | **NOT_PROVEN** — +1 of 32, p = 1.0 |
| TOKEN_EFFICIENCY | NON-INFERIOR — median +1.7%, not significant |
| DETAIL_COMPLETENESS | PASS — c07 and c08 ROOT in every arm |
| PONYTAIL / ADHD / COMBINED COEXISTENCE | PASS |
| DUPLICATE_RUNTIME / NORMAL_MODE_CLAIMED | NO / NO |
| BENCHMARK_INSTRUMENTS / INFRA separated from model failure | SELFTESTED (86 + 38 + 78) / YES |

**STATUS = NOT_READY_TO_MERGE** on the human-output gate alone. Everything else is green. The P2
sentence stays opt-in (`SAMEWRITE_OUTPUT_HOOK=1`), off by default; the default remains the
description-only skill, whose correctness and cost are non-inferior to the previous SameWrite (D vs B:
26 vs 25 ROOT, 23 vs 22 human_ok). The Owner may still merge as an experimental release with these
labels; this report does not call it merge-ready.
