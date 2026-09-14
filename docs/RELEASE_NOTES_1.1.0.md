# SameWrite 1.1.0 — release notes (draft; no tag or GitHub Release until `main` carries it)

**One sentence.** One canonical `samewrite` skill that spends a coding agent's tokens where they
matter — context, tool output, edits, retries — and leaves evidence that can fail; the measurement
tools and every experiment behind the numbers ship with it, including the ones that lost.

## What is new

- **One canonical skill**: `skills/samewrite/SKILL.md` — context ladder (expand only to answer an
  open question; symbol-level tools first when present), ask only when the ambiguity is material,
  minimum correct change, root cause with bounded retries (two failed fixes → stop and reassess),
  verification scaled by risk × uncertainty, and a compact result-first output rule.
- **`edit-discipline` becomes a hidden compatibility alias** (`disable-model-invocation: true`):
  `/edit-discipline` still works for 1.0.0 users, it no longer costs listing bytes per turn, and the
  edit rule lives in one place.
- **Hardened installer / uninstaller**: POSIX quoting (paths with spaces), exact-path ownership
  (a foreign hook that merely shares the filename is never touched; the 1.0.0 entry form is
  recognised on upgrade, no duplicate), malformed `settings.json` left alone with a warning,
  `hooks/uninstall.sh`, `install.sh --human-output`.
- **Coexistence proven deterministically** with Ponytail, i-have-adhd, Caveman and rtk surfaces
  (`tests/test_coexist.py`, including the real Ponytail and i-have-adhd hooks running next to the
  installed skill). samewrite claims no mode phrase — not `normal mode`, not `stop …`.
- **Benchmark infrastructure that cannot lie by accident**: infrastructure failures (missing test
  runner, usage/internal errors, zero tests collected, all skipped, CLI failure, broken transcript)
  are `INFRA_ERROR`, excluded and counted — never a model failure. Every scorer is proven to turn
  RED on a planted bad fixture (86 + 38 + 78 self-test checks). `requirements-test.txt` declares the
  only test-time dependency; CI runs clean Python 3.9 and 3.12.
- **Generated adapters** for AGENTS.md / GEMINI.md readers (`tools/adapters.py`, drift-checked in
  CI) — INSTRUCTION_ONLY on those hosts.
- **Reference audits** of nine related projects at pinned commits (`docs/reference-audits/`), no
  code copied.
- **Optional human-output hook** (`bash hooks/install.sh --human-output`): one sentence injected at
  SessionStart (~170 bytes), off by default. See the known limitation.
- **Observer stays offline and private**: the guard ledger and `carry.py --history` hold aggregates
  only (no paths, prompts or content); nothing reads history into the model; nothing rewrites the
  skill — evidence-driven optimization, not self-learning.

## Measured (methodology in `docs/FINDINGS.md`, `docs/VNEXT.md`)

- 1,316 transcripts: Bash + Read results are 63.8% of session carry; 20.8% of overwrites were
  byte-identical (the guard denies them); the "≤3 change blocks" edit rule is net negative.
- 462 controlled A/B runs: one terseness sentence −22.7% / −19.6% output tokens (two languages,
  pre-registered); a 4.7 kB block adds −0.8% over the sentence.
- Confirmatory run for this release (16 fresh cases × 8 arms × 2 reps, 256 runs, 0 excluded):
  correctness 25–26/32 in every arm, non-inferior to 1.0.0; stacking with Ponytail / i-have-adhd /
  both lost no correctness.

## Known limitation (kept on purpose)

**Human-output improvement: NOT_PROVEN.** The one-sentence SessionStart policy met the human-output
contract on 24/32 runs vs 23/32 without it (p = 1.0); the earlier pilot's 7/8 vs 5/8 did not
replicate. It is safe and cheap, so it ships opt-in; it is not a measured optimization claim. Also:
one small model in the benchmarks; three fixtures were floors in every arm; the skill body is loaded
on `/samewrite` or when the model calls it, not automatically on every prompt; Windows untested;
OpenCode and Pi unsupported.

## Upgrade from 1.0.0

`/plugin update samewrite@samewrite` (or reinstall). `/edit-discipline` keeps working; `samewrite`
becomes the listed skill. If you installed the guard hook, rerun `bash hooks/install.sh` — it
recognises the 1.0.0 entry and adds nothing. `bash hooks/uninstall.sh` removes only samewrite's
entries.
