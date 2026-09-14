# Candidate verdicts

What the offline optimizer proposed, what happened when each proposal was actually tested, and why
two of them are not in 1.2.0. A losing candidate is kept here with its evidence: the point of a
proposal queue that cannot promote itself is that refusing a proposal is a normal outcome.

Specifications live in [`experiments/candidates/`](../experiments/candidates/). This file is the
decision record.

---

## `bash-output-shaping` — **REJECTED: duplicated by platform behaviour**

**The proposal.** Bash is the largest single source of session carry (62.1% over 32 sessions and
32,510 turns). The obvious candidate was a rule that bounds what Bash leaves in the model's
context while keeping the raw output retrievable.

**Why it was rejected.** The premise did not survive measurement. Claude Code already caps Bash
output and spills the remainder to a file, and the real distribution confirms the cap is doing its
job. Over **30,731 Bash results** in 400 recent transcripts:

| statistic | value |
|---|---|
| median | 449 B |
| p90 | 2,246 B |
| p99 | 6,217 B |
| maximum | 28,989 B |
| above 30 kB | **0 results, 0.0%** |

Not one result exceeded the documented cap. A SameWrite rule that capped Bash output would
re-implement what the host already does — which is one of this project's own
[retirement criteria](../experiments/candidates/README.md#retirement), applied to a candidate
before it shipped rather than years afterwards.

**What the measurement actually says.** Bash dominates carry by **accumulation**, not by size:
thirty thousand small results, each resident for the rest of the session. That is a different
problem from "Bash prints too much", and a rule shaped for the wrong one would have cost always-on
bytes and bought nothing.

**Two further reasons it could not have been delivered as proposed.** A rule placed in the skill
**body** never loads in headless runs — the body was invoked 0 times in 174 `claude -p` runs. A
rule placed in the **listing description** would add always-on bytes to every turn, which 1.2.0
explicitly refuses. Reproduce: `python3 experiments/aivos/bash_residue.py --max-files 400`.

**What survives.** The evidence invariant the candidate carried is now in every specification the
optimizer emits, including the carve-out that an earlier draft was missing: raw evidence must
survive, **except** secret material, which is redacted at capture and never retained verbatim.

---

## `listing-prune` — **DEFERRED: real, small, and not SameWrite's to make**

**The proposal.** Most of the skill listing is never invoked, and it is paid for on every turn.

**The measurement, which is real.** Across 1,639 transcripts in three profiles:

| fact | value |
|---|---|
| total listing | 30,009 B |
| entries never invoked | 70 of 82 |
| cold bytes | 24,002 B — **80.0% of the listing**, ~7,644 tokens resident on every turn |
| listing share of total carry | **2.30%** (28 B/turn) |

**Why it is deferred rather than promoted.** Three reasons, in order of weight:

1. **It is below the threshold that was fixed before the numbers were read.** 2.30% falls under
   the pre-registered `NEGLIGIBLE` boundary of 5%, and far under this rig's measured run-to-run
   noise. No experiment at this scale could confirm or refute the end-to-end benefit, so promoting
   it would mean shipping on a number that cannot be defended.
2. **The cold entries are not SameWrite's.** They belong to other plugins the user installed.
   SameWrite's own always-on cost is **415 bytes**. A tool that removed other people's skills to
   improve its own metric would be doing something nobody asked for.
3. **A cold entry in one role can be essential to another.** The cold-share number is an upper
   bound on waste in the scope that was measured, not a list of things to delete.

**What it is instead.** A documented recommendation: run `python3 tools/skills.py --markdown` on
your own transcripts and decide for yourself. That is a legitimate outcome, not a fallback — a
measurement layer is allowed to hand a person a number and stop.

---

## `noop-guard` — **OBSERVED: the field sample is still too small to judge**

The guard's own ledger has recorded 55 writes against a pre-set floor of 100. Below that floor the
optimizer reports the sample as too small rather than dressing it up as a finding either way. When
the floor is reached, the same code will report either `noop-guard-retain` or
`noop-guard-retire` — retirement is a first-class outcome, and the guard is not exempt from it.

---

## What none of this changed

No skill text, no hook, no configuration. `skills/` and `hooks/` are byte-identical to the
released `v1.1.0` tag. The optimizer proposed, measurement decided, and nothing promoted itself.
