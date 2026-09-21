# C3 — does reordering the listing description improve routing?

**No. `KEEP_CURRENT_DESCRIPTION`. Nothing shipped.**

Measured, not promised. Losing experiments stay published.

## 1. Question

SameWrite's listing description leads with what the skill *is* — "Precision layer for code
changes — …" — and puts the trigger sentence — "Use when editing existing code, fixing a bug,
…" — in the middle. A plausible hypothesis says a model scanning a crowded skill listing
weights the opening of an entry more heavily, so a trigger-first ordering would route better.

C3 tested exactly that, and nothing else.

## 2. Frozen baseline

    tag                   v1.4.1
    commit                bb64f6976a5e87040cda244105c9753692218cb3
    canonical body        7edec9f21e0bd50583e388e0bdc177f92ba8f0db6ce2bb61acd52b39d81e7767
    host                  Claude Code 2.1.278 (native binary; installed == upstream latest)
    models                claude-haiku-4-5 (primary), claude-sonnet-5

Isolated per run: fresh `HOME` and `CLAUDE_CONFIG_DIR`, the owner's `CLAUDE_*` / `SAMEWRITE_*` /
`ANTHROPIC_*` variables stripped, no owner settings, hooks, skills or plugins. Headless `-p`,
never `--bare`.

## 3. Treatment

| | chars | bytes | sha256 |
|---|---|---|---|
| A / A2 — released | 391 | 393 | `f46c2f75e329874224ad7622414bc3c87ec0989705a47d3bb8a6596e002c7346` |
| B — trigger first | 391 | 393 | `becd456f36e919d675bcaa0cb022e216cfa096dabebfa58a4f4b5477baa407b3` |

A **pure reorder**, verified mechanically: identical word multiset (zero differing tokens),
identical sentence set, sentence order changed, zero character and zero byte delta. The body is
byte-identical in every arm, and arm A reproduces the tagged `SKILL.md` byte for byte
(`d7c65ee5a449626352dcbd1a3da0e5b4ab822a3e62eeec40ba62daf6b3780139`).

Arms: `A` released · `A2` a byte-identical null control whose label never reaches the model ·
`B` trigger-first · `N` manual-only negative control (`disable-model-invocation: true`) ·
`X` explicit positive control (`/samewrite`). `N` and `X` are calibration, not candidates.

## 4. Task set

24 fixtures, frozen to disk before the first comparison run, with a recorded randomisation
seed: 6 positive-core, 3 positive-high-risk, 3 positive-micro, 5 negative-core, 3
negative-code-read-only, 4 boundary — **12 POSITIVE, 8 NEGATIVE, 4 BOUNDARY**. The routing
expectation is never shown to the model. Boundary fixtures are analysed separately and do not
count toward the decision gates.

## 5. Routing detector

Structured, not a grep. It separates the channels the host actually uses:

| channel | signature |
|---|---|
| skill listing | `attachment.type == "skill_listing"`, entries `- <name>: <description>`, **arriving in more than one chunk** |
| the user's own prompt | a `user` record whose content is a **string** |
| skill body injection | a `user` record whose content is a **text block** beginning `Base directory for this skill: …/skills/<name>` |
| model-initiated invocation | an assistant `tool_use` named `Skill` |
| compaction | a compact boundary |

Calibration: the explicit control was detected **16/16**; the `disable-model-invocation`
control **0/16**; and an adversarial fixture whose *prompt* contains the injection preamble plus
1,500 bytes of real body text is still **not** counted as a load. Five detector mutants each
flip the result as required, including a naive "grep the transcript" mutant.

Two detector defects were found and fixed before any comparison was trusted, because both would
have reported the experiment's central quantity wrongly: a body load can occur **without** a
`Skill` tool call, and the listing arrives in chunks so keeping only the last one loses the
entry.

## 6. Oracle validation

Every correctness oracle is deterministic — a test run, an exact string, an AST fact, a byte
comparison against the fixture's own start tree. Each was shown to go **green on a planted good
output and red on a planted bad one** before any paid run. No LLM judge anywhere. Total: 118
assertions, zero model calls.

## 7. Primary result

    SameWrite implicit body loads, over 148 scored A / A2 / B runs on two models:  0

| arm | scored | POSITIVE loads | NEGATIVE loads | BOUNDARY loads |
|---|---|---|---|---|
| A | 52 | 0/30 | 0/18 | 0/4 |
| A2 | 44 | 0/24 | 0/16 | 0/4 |
| B | 52 | 0/30 | 0/18 | 0/4 |

    A_TP = 0     A2_TP = 0     B_TP = 0
    A_FP = 0     A2_FP = 0     B_FP = 0

    B_VS_A_ROUTING_DELTA = 0.0 pp        NULL_ROUTING_DELTA = 0.0 pp
    treatment-not-exposed 0 · compaction-contaminated 0 · infra errors 0

The description was verifiably in front of the model on all 148 runs — the full 391 characters,
hash-matched to the arm under test.

**The zero is not a dead instrument.** A synthetic skill carrying a deliberately loud,
task-targeted description was placed beside SameWrite and was implicitly invoked **5 of 5
times** across both models, through the `Skill` tool, and the detector saw every one. Implicit
routing works here. What is rare is *this* description firing: roughly **1 load in ~70
opportunities**, and identical between the two orderings everywhere it was measured.

## 8. Body-utility check

Before asking whether routing should be made *more* aggressive: does loading the body help this
task class at all? Arm A against the explicit arm X, 8 fixtures × 2 replicates.

    correctness   A 15/16     X 15/16       one gain for X, one regression for X
    high-risk     A  6/6      X  5/6
    X loaded the body on 16 of 16 runs

On the 14 pairs where both arms completed correctly, X spent **1,569 fewer output tokens
(−8.2%)**, 5 fewer tool calls and 3 fewer turns, and **16,547 more cache-creation tokens
(+9.5%)** — the 4,385-byte body entering context. Priced with this repository's own weights,
**+2.49%** overall.

    BODY_UTILITY_CEILING = MIXED

Loading the body made the model terser and no more correct, at slightly higher total cost. A
description change whose purpose is to load the body more often is therefore optimising toward
an outcome this corpus does not reward.

## 9. Crowded-listing result

The per-entry description cap documented upstream is **1,536 characters**; SameWrite's 391 is a
quarter of it, so there is nothing to truncate at the entry level. Controlled crowding with
synthetic, never-invoked filler skills:

| total entries | listing bytes | SameWrite entry | A | B |
|---|---|---|---|---|
| 25 | 15,211 | **FULL**, 391 chars | same | same |
| 49 | 19,546 | **FULL**, 391 chars | same | same |
| 133 | 8,028 | **NAME_ONLY**, 0 chars | same | same |
| 313 | 10,908 | **NAME_ONLY**, 0 chars | same | same |

Past the pressure point the listing *shrinks* while carrying five times as many entries: the
host keeps a few entries in full and reduces every other one — SameWrite included — to a bare
`- name`. Both arms are stripped identically.

    CROWDED_RESULT = WHOLE_DESCRIPTION_PRUNING_DOMINATES
    DESCRIPTION_REORDER_CANNOT_FIX_WHOLE_DESCRIPTION_REMOVAL = YES

The host does not expose a prefix under pressure, which is the one condition that would have
earned a trigger-first ordering any truncation-resilience credit.

## 10. Model sensitivity

The treatment gives the same answer on both models: zero against zero. The *mechanism* does not.
Claude Sonnet 5 invoked SameWrite implicitly once in an isolated two-run probe; Claude Haiku 4.5
never did across 24 fixtures. Implicit routing of this description is a rare, model-dependent
event.

## 11. Limits and adaptive deviations

    HEADLESS_PRIMARY      = YES
    INTERACTIVE_ROUTING   = UNTESTED
    CLAUDE_CODE_VERSION   = 2.1.278

**This was not a purely pre-registered confirmatory sequence, and saying so matters more than
the result.** The primary model was chosen as the lowest-cost accessible one that met every
stated criterion, and it then turned out never to route this description at all — so the first
stage had no power to discriminate any ordering. **The second model stage was an adaptive
replication after the first stage showed no useful implicit-routing signal.** It returned the
same zero.

Other limits, stated rather than buried: 24 small, mostly single-file fixtures; one replicate
for the primary comparison; two models; headless only; the crowding pressure point bracketed
between 49 and 133 entries rather than bisected; filler skills sharing a naming prefix and
subject register.

199 model runs against a pre-set budget of 200.

## 12. Product decision

    C3_VERDICT             = KEEP_CURRENT_DESCRIPTION
    V1_5_RELEASE_JUSTIFIED = NO

Three pre-registered gates fail: the routing signal (≥ 20 pp above null), utility, and null
stability. Any one of them blocks promotion. The released description is unchanged, byte for
byte.

### What this does not say

- **Not** that SameWrite's auto-routing never works. A loud description routed 5 of 5.
- **Not** that the skill body is useless. The ceiling shows a real output-token and turn
  reduction; what it does not show is a correctness gain.
- **Not** that all models behave this way. One of the two tested did route it, once.
- **Not** that interactive Claude Code routes at zero. That was never tested.
- **Not** that Codex, Hermes or OpenClaw route at zero. Those were never measured.

### Do not reopen without new evidence

C3 closes the routing question and the finalization audit closed the rest of the optimization
workstream. Each of these is rejected or deferred on measurement, with the condition that would
reopen it:

| not built | revisit only if |
|---|---|
| trigger-first description reorder | host routing semantics materially change, or a model family shows reproducible order sensitivity |
| C4 body shrink | a real body-level failure appears, or a measurable body-cost problem does |
| custom Read guard | a supported host removes its own Read bound and unbounded Reads dominate carry |
| repeat-read dedup hook | repeated identical Reads become a top-three carry bucket |
| large SessionStart injection | a host makes on-demand body loading impossible |
| Bash compressor | a real corpus shows Bash-result p90 above roughly 30 kB |
| SameWrite memory | a measured failure that only cross-session memory could fix |
| automatic compact trigger | a host exposes a supported, observable compaction API and agent-chosen timing beats the host's |
| automatic promotion · automatic persistence · self-editing policy | never under the current governance model |
| mandatory SameWrite invocation in an AI-VOS lane | a larger pre-registered AI-VOS workload shows a correctness or cost benefit beyond null variability |
| generic savings claim | corrected-accounting raw transcripts are preserved and a frozen A/B design is run |

`TOTAL_SAVINGS` remains **NOT_PROVEN**, and nothing in C3 changes that.
