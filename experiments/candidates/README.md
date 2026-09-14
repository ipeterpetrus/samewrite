# Candidates — evidence that has not become policy

A candidate is an observation with a hypothesis attached. Nothing in this directory changes how
SameWrite behaves: `tools/optimize.py` writes these files, and it never edits `skills/`, `hooks/`
or any configuration (proved in `tests/test_optimize.py` by hashing those trees around a run).

## Lifecycle

| state | meaning | who moves it forward |
|---|---|---|
| `OBSERVED` | a measurement crossed nothing; recorded so the next run can see it again | the optimizer |
| `HYPOTHESIS` | someone wrote down what they think causes it and what would change | a human |
| `CANDIDATE` | evidence cleared the pre-set threshold; an experiment is justified | the optimizer proposes, a human decides |
| `EXPERIMENTAL` | implemented and measured on development fixtures | a human or an authorised builder |
| `PROVEN` | it beat the incumbent on held-out fixtures under the promotion gate | a human, in a pull request |
| `REJECTED` | it was measured and did not win — kept, because a losing experiment is evidence | anyone |

No state is skipped. In particular, nothing goes from `OBSERVED` to production, and no tool
promotes anything: promotion is a pull request a person opens, reviews and merges.

## Promotion gate

A candidate may be recommended for promotion only when all of these hold, on fixtures that were
**not** used to invent the rule:

```text
CORRECTNESS_NON_INFERIOR   SAFETY_NON_INFERIOR   TOTAL_COST_IMPROVED
VERIFIER_SELFTEST          HELD_OUT_CONFIRMATION
NO_PRIVACY_REGRESSION      NO_COEXISTENCE_REGRESSION
```

Total cost means correct result per total task cost — input, cache, output, tool bytes, turns,
retries, rework, wall time. A rule that saves output tokens and adds one failed attempt is not an
improvement, and the gate is written so that it cannot be read as one.

## Instruction budget

Every candidate records an `always-on bytes delta`. A candidate that adds persistent text must
show that `added_bytes × expected_turns` is smaller than the measured saving **and** name a rule
it replaces or compresses. SameWrite is supposed to get smaller or stay the same size while it
gets better; accumulation is the failure mode this budget exists to prevent.

## Retirement

Removal is a first-class candidate. A rule becomes a retirement candidate when it has no
measurable benefit, carries persistent cost, is duplicated by platform behaviour, is superseded by
deterministic tooling, or creates coexistence friction. `tools/optimize.py` already emits one:
`noop-guard-retire`, when the guard's own field ledger shows it is no longer preventing enough.
