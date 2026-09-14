# Candidate: listing-prune

state: CANDIDATE (see experiments/candidates/README.md for the lifecycle)
date: 2026-09-14

## Observation

most of the skill listing is never invoked — 70/82 entries never invoked, 24,002 of 30,009 listing bytes (80.0%)

## Hypothesis

uninstalling never-invoked plugins removes always-on carry with no loss

## Incumbent

SameWrite as released, unchanged.

## Candidate

To be written by a human or an authorised builder. This file is evidence and a specification;
nothing here changes runtime behaviour.

## Primary metric

cold share of the skill listing — reported with correctness and total task cost, never alone.

## Correctness gate

Correctness non-inferior to the incumbent on the same fixtures; safety-sensitive fixtures
(security, destructive) non-inferior.

## Instruction budget

always-on bytes delta: -24002. A candidate that adds always-on text must
show `added_bytes × expected_turns` is smaller than the measured saving, and must name a rule it
replaces or compresses.

## Risk

a description can route without ever being loaded — an upper bound on waste

## Affected layer

user configuration, not SameWrite text

## Benchmark required

uninstall one, measure the listing and the outcome

## Promotion criterion

CORRECTNESS_NON_INFERIOR and SAFETY_NON_INFERIOR and TOTAL_COST_IMPROVED and VERIFIER_SELFTEST
and HELD_OUT_CONFIRMATION and NO_PRIVACY_REGRESSION and NO_COEXISTENCE_REGRESSION — all of them,
on fixtures that were not used to invent the rule.
