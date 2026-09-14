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

Against `0aec7ce` (`git diff --stat`), all local, nothing pushed:

```
.claude-plugin/marketplace.json              |   2 +-
 .claude-plugin/plugin.json                   |   2 +-
 .github/workflows/test.yml                   |  10 +-
 .gitignore                                   |   2 +
 README.md                                    |  36 ++++-
 adapters/AGENTS.samewrite.md                 |  56 ++++++++
 adapters/GEMINI.samewrite.md                 |  56 ++++++++
 docs/VNEXT.md                                | 335 +++++++++++++++++++++++++++++++++++++++++++
 docs/reference-audits/aider.md               |  44 ++++++
 docs/reference-audits/caveman.md             |  48 +++++++
 docs/reference-audits/i-have-adhd.md         |  46 ++++++
 docs/reference-audits/ponytail.md            |  54 +++++++
 docs/reference-audits/rtk.md                 |  49 +++++++
 docs/reference-audits/serena.md              |  57 ++++++++
 docs/reference-audits/superpowers.md         |  55 +++++++
 docs/reference-audits/token-savior.md        |  41 ++++++
 experiments/vnext/PREREGISTRATION.md         |  85 +++++++++++
 experiments/vnext/README.md                  |  23 +++
 experiments/vnext/analyze.py                 |  89 ++++++++++++
 experiments/vnext/fixtures.py                | 325 ++++++++++++++++++++++++++++++++++++++++++
 experiments/vnext/rescore.py                 |  22 +++
 experiments/vnext/rig.py                     | 264 ++++++++++++++++++++++++++++++++++
 experiments/vnext/runs/manifest.json         |  58 ++++++++
 experiments/vnext/runs/pilot1.jsonl          | 110 ++++++++++++++
 experiments/vnext/runs/pilot1.rescored.jsonl | 110 ++++++++++++++
 experiments/vnext/runs/smoke.jsonl           |   4 +
 experiments/vnext/selftest.py                | 133 +++++++++++++++++
 hooks/install.sh                             |  56 +++++++-
 hooks/samewrite_mode.py                      | 126 +++++++++++++++++
 hooks/uninstall.sh                           |  51 +++++++
 hooks/write_noop_guard.py                    |  14 +-
 skills/samewrite/SKILL.md                    |  60 ++++++++
 tests/test_adapters.py                       |  75 ++++++++++
 tests/test_coexist.py                        | 362 +++++++++++++++++++++++++++++++++++++++++++++++
 tests/test_samewrite_mode.py                 | 155 ++++++++++++++++++++
 tests/test_write_noop_guard.py               |   3 +
 tools/adapters.py                            |  61 ++++++++
 37 files changed, 3066 insertions(+), 13 deletions(-)
```

Untouched on purpose: `skills/edit-discipline/SKILL.md`, every `tools/*.py` except the new `adapters.py`, `experiments/skill-ab/`, `docs/FINDINGS.md`, `docs/FIELD_DATA.md`, `LICENSE`.
