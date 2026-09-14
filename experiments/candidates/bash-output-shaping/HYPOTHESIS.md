# Candidate: bash-output-shaping

state: CANDIDATE (see experiments/candidates/README.md for the lifecycle)
date: 2026-09-14

## Observation

Bash dominates carry — Bash is 61.2% of carry over 168 sessions / 110,651 turns

## Hypothesis

ask Bash for the answer, not the log: failures-only, bounded output, counts instead of listings lowers total task cost without lowering correctness

## Incumbent

SameWrite as released, unchanged.

## Candidate

To be written by a human or an authorised builder. This file is evidence and a specification;
nothing here changes runtime behaviour.

## Primary metric

carry share of Bash — reported with correctness and total task cost, never alone.

## Correctness gate

Correctness non-inferior to the incumbent on the same fixtures; safety-sensitive fixtures
(security, destructive) non-inferior.

## Instruction budget

always-on bytes delta: +0. A candidate that adds always-on text must
show `added_bytes × expected_turns` is smaller than the measured saving, and must name a rule it
replaces or compresses.

## Risk

a rule that shortens evidence can raise retries

## Affected layer

skill body (no always-on bytes)

## Benchmark required

paired fixtures, correctness gate first, then total cost

## Promotion criterion

CORRECTNESS_NON_INFERIOR and SAFETY_NON_INFERIOR and TOTAL_COST_IMPROVED and VERIFIER_SELFTEST
and HELD_OUT_CONFIRMATION and NO_PRIVACY_REGRESSION and NO_COEXISTENCE_REGRESSION — all of them,
on fixtures that were not used to invent the rule.
