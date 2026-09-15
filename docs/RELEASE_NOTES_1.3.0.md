# SameWrite 1.3.0 — release notes

**One sentence.** SameWrite now installs natively on four coding-agent hosts with one command each,
from a single canonical skill whose policy body is byte-identical everywhere.

**The headline feature of this cycle did not ship.** A persistent status-reporting rule was designed,
pre-registered, benchmarked over 130 runs, and refused by its own gate. That is in here too.

## What changed

- **Four verified hosts.** Claude Code, Codex, Hermes Agent and OpenClaw each install and load the
  skill, each proven in an isolated profile by this repository's own acceptance scripts.
- **One command per host**, every one executed exactly as published:

  ```text
  Claude Code   claude plugin marketplace add ipeterpetrus/samewrite && claude plugin install samewrite@samewrite
  Codex         codex  plugin marketplace add ipeterpetrus/samewrite && codex  plugin add     samewrite@samewrite
  Hermes Agent  hermes skills install https://raw.githubusercontent.com/ipeterpetrus/samewrite/v1.2.1/adapters/hermes/samewrite/SKILL.md --yes
  OpenClaw      d=$(mktemp -d) && curl -fsSL https://github.com/ipeterpetrus/samewrite/archive/refs/tags/v1.2.1.tar.gz | tar -xz -C "$d" \
                && openclaw skills install "$d"/samewrite-*/skills/samewrite && rm -rf "$d"
  ```

  The raw-URL routes are pinned to a release tag rather than `main`. Claude Code and Codex use
  their own package managers.
- **A portable AgentSkills surface.** `adapters/agentskills/samewrite/SKILL.md` is generated,
  byte-identical to the canonical file, and contains only spec-valid frontmatter.
- **The Claude-only alias stops travelling.** `disable-model-invocation` is rejected by the
  AgentSkills reference validator and *silently ignored* by Codex — which would un-hide the alias
  and charge a user catalog bytes for something that exists only for Claude 1.0.0 upgraders.
  `.codex-plugin/plugin.json` now points Codex at the portable surface instead of at `skills/`.
  Packaging diverges; behaviour does not.
- **`tools/doctor.py`** — read-only, no network, no model. Every line is something it checked;
  anything it cannot see says `NOT_OBSERVABLE` rather than showing a green mark.
- **AI-VOS readiness**, proven against the canonical state with a planted canary: 27/27, zero
  mutation of the governed workspace, proposal-only optimizer.

## Policy body, identical everywhere

```text
CLAUDE              009dc957105231f0   4,311 B   description 391 chars
CODEX / AGENTSKILLS 009dc957105231f0   4,311 B   description 391 chars
HERMES              009dc957105231f0   4,311 B   description  49 chars
OPENCLAW            009dc957105231f0   4,311 B   description 391 chars
```

Hermes truncates a skill description to 60 characters in its prompt, so its adapter shortens **that
field only**. One canonical behaviour, four packagings.

## The truth experiment: NOT_PROMOTED

A 157-byte sentence asking the agent not to report an action as done unless it observed it. Five
arms, 24 traps plus 2 positive controls, 130 runs, zero infrastructure errors, order randomised
under a recorded seed, pre-registration frozen by hash before the first run.

**The null calibration passed first** — two identical treatments scored 4/24 against 4/24,
p = 1.000 — so this is a real negative, not an inconclusive one. Candidates moved 4/24 → 3/24 at
p = 1.000, nowhere near the pre-registered 30% reduction. **No rule was added to SameWrite.**

The reason is a floor, not a dud: only 7 of 24 traps ever caught any arm. The rule did nearly double
how often the answer named the missing evidence, and caused **zero** false failures on both positive
controls. What it could not do is reduce claims that were already rare.

The more useful finding is where the remaining failures sit — truncated tool output, version
mismatch and conflicting evidence, 14 of 18. Two of those are *evidence-sampling* problems rather
than reporting ones, and a one-sentence reporting rule is the wrong instrument for them. That is a
future research direction, not a feature in this release.

Full write-up: [experiments/truth/RESULTS.md](../experiments/truth/RESULTS.md).

## One real, local saving

Repairing a real profile removed a hand-copied 1.0.0-era skill that had lost its hiding flag:
listing 25,334 → 25,083 bytes, **−251 B per turn**. That is a configuration saving on one machine,
not a SameWrite universal saving, and it is labelled that way everywhere it appears.

## Known limitations, stated plainly

| | |
|---|---|
| overall end-to-end token savings | **NOT_PROVEN** — best measurement −1.7%, 8/10 fixtures, p = 0.109, below the rig's own noise |
| "best in the world" | **NOT_TESTED** — no comparative benchmark was run, so no such claim is made |
| Codex unused-body cost | **NOT_OBSERVABLE** — measuring it would mean intercepting a prompt the host does not expose |
| Hermes observer | **DEFERRED_BY_SCOPE** — feasible and audited, deliberately not built: see [docs/HERMES_OBSERVER.md](HERMES_OBSERVER.md) |
| OpenClaw observer | **UNTESTED** |
| the truth rule | **NOT_PROMOTED** — designed, tested, refused by its own gate |
| Windows | **UNTESTED** |
| ClawHub distribution | blocked — no CLI and no authenticated publisher identity on this machine; the pinned tarball route is used instead |

## Unchanged

The canonical skill and the Claude hooks are byte-identical to `v1.1.0`. The observer still adds
zero bytes to a model's context, still makes zero model calls, still opens no socket, and still
promotes nothing on its own.
