# samewrite

**Spend tokens on reasoning, not repetition.**

SameWrite is an evidence-driven efficiency skill for coding agents: less avoidable context, tool
noise, editing and retry work, without trading away correctness.

**Measured, not promised. Losing experiments stay published.**

## Install — one command per host

| host | install | invoke |
|---|---|---|
| **Claude Code** | `claude plugin marketplace add ipeterpetrus/samewrite && claude plugin install samewrite@samewrite` | `/samewrite` |
| **Codex** | `codex plugin marketplace add ipeterpetrus/samewrite && codex plugin add samewrite@samewrite` | `$samewrite`, or let it route on the description |
| **Hermes Agent** | `hermes skills install https://raw.githubusercontent.com/ipeterpetrus/samewrite/v1.4.1/adapters/hermes/samewrite/SKILL.md --yes` | `/samewrite` |
| **OpenClaw** | `(d=$(mktemp -d) && trap 'rm -rf "$d"' EXIT && curl -fsSL https://github.com/ipeterpetrus/samewrite/archive/refs/tags/v1.4.1.tar.gz \| tar -xz -C "$d" && openclaw skills install "$d"/samewrite-*/skills/samewrite)` | `$samewrite` or `/skill samewrite` |

Every command above was executed against the real host in an isolated home or state directory, and
is reported only because it worked there. The OpenClaw line additionally runs its download, extract
and install steps inside a subshell with an `EXIT` trap: a failed download, a corrupt archive or a
refused install all clean up after themselves, and your own shell traps are untouched
(`bash tests/test_oneliner_cleanup.sh` forces each of those failures offline). The two raw-URL
routes are **pinned to a release tag**, not to `main`, so what you install today is what you
inspected. Claude Code and Codex use their own package managers, with their own update semantics.

The pinned URLs name **the same version as this README**: read this file at tag `v1.4.1` and the
commands install `v1.4.1`. That is the whole point of pinning — nobody should end up installing a
version other than the one whose text they just read. `python3 tests/test_install_paths.py` checks
that pairing offline, which is also how a release branch catches a stale pin before anyone
publishes it.

After installing on Claude Code, **start a new session** — a running session cannot pick up a skill
that was installed after it started.

```bash
python3 tools/doctor.py     # what is actually installed, observed rather than assumed
```

## Supported hosts

| host | core skill | unused body | host-specific extras | observer | tested against |
|---|---|---|---|---|---|
| Claude Code | **VERIFIED** | 0 B body · 405-char listing entry[^listing] | write no-op guard, optional output sentence | generic offline | skill/routing surface 2.1.278; hook acceptance 2.1.271 |
| Codex | **VERIFIED** | `NOT_OBSERVABLE` | native plugin, no hooks | generic offline | codex-cli 0.153.2 |
| Hermes Agent | **VERIFIED** | 0 B body · 80 B listing | none | `DEFERRED_BY_SCOPE` | 0.21.3 / `437116f` |
| OpenClaw | **VERIFIED** | 0 B body · ~440 B catalog | none | `UNTESTED` | 2026.9.4 / `388f57a` |

The write guard and the output sentence are **Claude Code hooks**. They are not ported to the other
hosts and are not claimed there. The skill body is identical everywhere, and that is checked rather
than asserted: `BODY_SHA256` — every byte after the closing front-matter delimiter — is
`7edec9f21e0bd505…` on all four hosts (`python3 tools/adapters.py --hashes`). The *file* hashes
differ, because front matter is exactly what a host shapes: where a host caps its routing
description, the adapter shortens **that field only**.

Codex's unused-body cost is `NOT_OBSERVABLE` rather than a number, because measuring it would mean
intercepting a prompt the host does not expose. Native support is verified independently of it.

## Turning things on and off

| component | default | on | off | model-context cost |
|---|---|---|---|---|
| SameWrite core | installed = discoverable; body loads on demand | host install command above | uninstall via the host | listing entry only until invoked |
| Claude write no-op guard | **off** | `bash hooks/install.sh` | `bash hooks/uninstall.sh` (removes every SameWrite hook entry, not the guard alone) | 0 prompt bytes — a deterministic hook |
| Claude compact output sentence | **off** | `bash hooks/install.sh --human-output` | `bash hooks/uninstall.sh` | ~170 B once per session. **NOT_PROVEN** to improve anything |
| observer / history | manual | `python3 tools/carry.py --history ~/logs/carry_history.jsonl` | stop invoking it | **0** |
| optimizer | manual | `python3 tools/optimize.py` | stop invoking it | **0**, and zero model calls |
| v1.4 shadow evaluation | manual | `python3 tools/evidence_shadow.py <history>` | stop invoking it | **0**, and it writes nothing at all |

There are no modes. Nothing runs in the background, nothing is scheduled, and no daemon is
installed. "Off" means you do not run it.

## v1.4 — typed evidence, and what it deliberately does not do

1.4 replaces the optimizer's untyped aggregates with a typed evidence kernel. None of it runs on
its own, and none of it changes what a model sees.

**Added**

| | |
|---|---|
| typed evidence acquisition | a sweep produces a certificate of what it actually read, not a total |
| history schema 4 | the current write format: chained records carrying position and the digest of the record before them |
| legacy read, fail-closed | schema 0/1/2/3 are read, counted and attributed; facts their schema never carried stay ABSENT, and a container holding one is `UNVERIFIED` — legacy evidence cannot gain current trust by defaulting |
| global container integrity | one container, one integrity answer, independent of which records a finding happens to look at |
| acquisition integrity as its own axis | `INTACT` · `BOUNDED` (a bound someone chose) · `DEGRADED` (a loss nobody chose) · `FAILED` · `UNVERIFIED` |
| analysis sufficiency as a separate axis | "the evidence is intact" and "there is enough of it" are different questions, answered separately |
| tombstones for failed acquisition | a sweep that read nothing writes a tombstone, not a measurement with no shares |
| privacy-safe provenance | sizes, shares and digests; no paths, prompts or content |
| shadow evaluation | `listing_cost` and `write_guard_retirement`, evaluated read-only and reported |

**Intentionally not active in 1.4.1**

automatic promotion · automatic candidate persistence · automatic policy mutation · windowing ·
host-shift gating · `carry_share_concentration` · `carry_bytes_trend`

v1.4 measures and evaluates evidence in shadow mode; automatic v1.4 candidate promotion and
persistence remain intentionally disabled while the transaction and API boundary around them is
still being researched. "Ready" in the output below is a statement about the evidence — never a
statement that anything was written.

```bash
python3 tools/evidence_shadow.py ~/logs/carry_history.jsonl --scope default
```

One row per retained finding — container state, acquisition integrity, sufficiency, whether it
would promote and why not — then exit 0 whatever it found. It writes no candidate, no artifact and
no file: a shadow that failed the run would already be a decision.

## The strongest measured facts

| measured | number | scope |
|---|---|---|
| where a session's tokens actually go | Bash + Read results **63.8%** of carry | 1,316 Claude Code transcripts, 237,541 turns [^acct] |
| overwrites byte-identical to what is already on disk | **20.8%** (154/741) — the guard denies them | same corpus |
| one terseness sentence vs no instruction | **−22.7%** output tokens, facts kept 100% | pre-registered A/B, 16 pairs |
| the same intent as a 4.7 kB always-on block | **−0.8%** over the sentence, p = 0.86 | pre-registered A/B |
| observer added to a model's context | **0 bytes** | hashed policy tree, 80 transcripts |
| Hermes unused skill body | **0 bytes** | isolated profile, 11/11 checks |
| removing one stale hand-copied skill from a real profile | **−251 B per turn** | one machine's configuration, not a product saving |

[^listing]: Three different quantities, kept apart. The frontmatter **description** is **391 characters / 393 UTF-8 bytes**. The **listing entry** — the `- samewrite: …` line the host injects, measured the way `tools/skills.py` measures every entry — is **405 characters / 407 UTF-8 bytes**, observed in an isolated Claude Code 2.1.278 configuration. The 415 this table carried before was the same measurement taken against an earlier description; the method is unchanged, the description is not.

[^acct]: The **63.8%** is a share and it survives the v1.4.1 accounting correction — re-measured,
    it moves by 0.047 pp. The **237,541 turns** beside it does not: until v1.4.1 the parsers
    counted one turn per JSONL record, and Claude Code writes one record per content block, so
    that count is inflated about 1.95x. It is left as published rather than quietly restated,
    because its August-2026 corpus no longer exists to recount. Full re-derivation:
    [docs/MEASUREMENT_CORRECTION_1_4_1.md](docs/MEASUREMENT_CORRECTION_1_4_1.md). Found by
    [roy-tong](https://github.com/ipeterpetrus/samewrite/issues/1) in public issue #1.

**Overall end-to-end token savings remain `NOT_PROVEN`.** The best measurement is −1.7%, cheaper on
8 of 10 fixtures at p = 0.109 — smaller than the same rig's variance between two byte-identical
arms. It is published in full under [evidence](#experiments-that-lose-stay-published) rather than
rounded into a headline.

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
| listing description | host-provided discovery surface; present while the host keeps that listing (391 chars) | routing hint; the only text SameWrite puts in front of the model by default. Not a permanent post-compaction guarantee — what the host does to the listing after an auto-compact is untested here |
| `SKILL.md` body | no — loads on `/samewrite` or when the model invokes it | `/samewrite` is a **deterministic load**, not a promise of better results: it loaded the body on 16 of 16 measured runs, while implicit invocation fired roughly once in seventy opportunities ([C3](docs/C3_ROUTING_EXPERIMENT_v1_4_1.md)) |
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
| a 4.7 kB always-on instruction block vs one sentence | **−0.8%, p = 0.86** — the big block bought nothing | it is the reason the skill body is on-demand and the listing entry is 405 characters |
| the optional human-output hook | **NOT_PROVEN** over 256 pre-registered runs | it stayed opt-in and off by default instead of shipping on a hunch |
| vNext cost improvement over the previous skill | **within noise** | correctness was non-inferior, so the release shipped on correctness, not on a cost claim |
| `bash-output-shaping`, the strongest candidate the optimizer found | **REJECTED — duplicated by platform behaviour** | 30,731 real Bash results: median 449 B, p90 2,246 B, **none above 30 kB**. The host already caps and spills to a file. See [docs/CANDIDATES.md](docs/CANDIDATES.md) |
| the AI-VOS role matrix, 80 runs on Opus 5 | **NOT_PROVEN** | two byte-identical arms differed by more than any effect measured, so the honest answer is that this rig cannot resolve it at this sample size |
| a persistent status-reporting rule, 130 runs on Opus 5 | **NOT_PROMOTED** | we tested whether one sentence could reduce unsupported success claims. It did not meet the pre-registered threshold, so no rule shipped. The baseline was already 4/24, and the remaining failures clustered in evidence *sampling* — truncated output, version mismatch, conflicting state — not in wording. See [experiments/truth/RESULTS.md](experiments/truth/RESULTS.md) |
| trigger-first routing description, 199 runs on Claude Haiku 4.5 and Sonnet 5 | **KEEP_CURRENT_DESCRIPTION** — **0.0 pp** routing change | a pure 391-character reorder moved implicit loading by nothing at all across 148 scored runs, against a byte-identical null control, in the tested headless configuration. Under a crowded listing the host strips the whole description to a bare name, so ordering has nothing left to act on. v1.5 is not justified by this experiment. See [docs/C3_ROUTING_EXPERIMENT_v1_4_1.md](docs/C3_ROUTING_EXPERIMENT_v1_4_1.md) |

## How it compares

Nine projects, read at pinned commits by read-only audits kept in
[`docs/reference-audits/`](docs/reference-audits/). Every cell below is either something an audit
states or a dash meaning **the audit does not say** — a dash is not a "no". No project is ranked
against another here, because no experiment in this repository compares them head to head.

Legend: ● audited yes · ○ audited no · – not in the audit

| | primary job | always-on cost | mech. hooks | measures itself | evidence loop | presentation | build minimalism | tool-output filtering | symbol navigation | per-scope isolation |
|---|---|---|---|---|---|---|---|---|---|---|
| **samewrite** | cheapest correct, verified change | **407 B** (measured)[^listing] | ● `PreToolUse(Write)` deny-if-identical | ● pre-registered, scorers self-tested, in CI | ● offline, proposes only | ● one output rule | ○ | ○ | ○ | ● scope / workload |
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
  407 B and superpowers' 3,308 B are measured injected bytes.
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
| **NOT_PROMOTED** | a persistent status-reporting rule. Tested over 130 runs on a benchmark whose null calibration passed; it did not meet the pre-registered threshold, so nothing shipped |
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

See [Supported hosts](#supported-hosts) at the top. Labels used there, and what each one costs to
earn:

| label | means |
|---|---|
| `VERIFIED` | installed and exercised on that host in an isolated profile, by this repository's own acceptance script |
| `DEFERRED_BY_SCOPE` | possible, audited, deliberately not built — see [docs/HERMES_OBSERVER.md](docs/HERMES_OBSERVER.md) |
| `UNTESTED` | not run; never inferred from another host |
| `NOT_OBSERVABLE` | the host does not expose what would have to be measured |
| `INSTRUCTION_ONLY` | a generated instruction file, not a loaded skill |

Codex / OpenCode via `adapters/AGENTS.samewrite.md` and Gemini CLI via `adapters/GEMINI.samewrite.md`
remain `INSTRUCTION_ONLY`. Windows paths are `UNTESTED`; POSIX paths with spaces and metacharacters
are tested.

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
tools/msgid.py              one assistant message, however many JSONL records carry it — the
                            identity law every counter above calls (public issue #1)
                            measure your own transcripts (read-only, stdlib only)
tools/optimize.py           read those aggregates offline: where cost is concentrated, what moved,
                            and whether anything justifies an experiment — or NO_ACTION
                            (--scope-id keeps several agents' populations apart; see docs/MULTI_AGENT.md)
tools/evidence/ · wire/     the frozen v1.4 evidence kernel, ported byte for byte (35 files)
tools/evidence_acquire.py · evidence_history.py   typed acquisition; schema 4 written, 0-3 read
tools/evidence_shadow.py    what each retained finding WOULD see — printed, never persisted
experiments/                skill-ab (462 runs) · vnext (110) · presentation (64 pilot + 256 confirmatory)
                            — rigs, fixtures, self-tests, pre-registrations, every run ever scored
experiments/scale/          how the sweep scales (1k and 10k sessions) and why there is no index
docs/VNEXT.md               build report · docs/RELEASE_NOTES_1.1.0.md · _1.2.0.md · _1.2.1.md · _1.3.0.md · _1.4.0.md · _1.4.1.md
                            docs/reference-audits/ — nine projects read at pinned commits
docs/MULTI_AGENT.md         many agents, running all the time · docs/AI_VOS_PROFILE.md (one profile)
docs/EVIDENCE_CONTRACT_V1_4.md   the frozen contract the kernel implements
tests/                      1601 assertions in seventeen suites, mutation-tested; CI on Python 3.9 and 3.12
                            plus two shell suites: the OpenClaw one-liner's cleanup, the OpenClaw host
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
an incomplete sweep cannot produce a candidate; and when a human passes `--emit-candidate`,
candidate ids are deterministic, so a scheduler that calls this hourly writes no duplicate
proposals. Without that flag nothing is written at all — a scheduled run reports and stops — and
v1.4's own promotion path, the one that would write a candidate from typed evidence, is not active
in this release at all. Contract, exit codes and the measured resource budget:
[docs/MULTI_AGENT.md](docs/MULTI_AGENT.md).

Run the suites: `python3 -m pip install -r requirements-test.txt` (pytest is the only test-time
dependency; the runtime is standard library) then `for t in tests/test_*.py; do python3 $t; done`.
`experiments/*/selftest*.py` prove the benchmark scorers can fail.

Support: none promised. A measurement result with tooling attached, published because the
negative findings are useful.

## License

MIT
