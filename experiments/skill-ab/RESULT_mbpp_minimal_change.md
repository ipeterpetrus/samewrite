# Result: frozen third-party minimal-change study

The registered prediction **failed**. This was a completed 40-run study, not an aborted
one: each of the 20 frozen, mechanically selected MBPP tasks was run once in each arm.
The protocol and task-selection rule were committed before this data file existed in
[`PREREGISTRATION_mbpp_minimal_change.md`](PREREGISTRATION_mbpp_minimal_change.md) at
`ed366d8`.

## Gate and primary result

The registered correctness gate removed four pairs: MBPP 60, 122, 131, and 136. The first,
second, and fourth had failed or empty output in both arms; MBPP 131 failed or was empty in
the `oneline` arm. No substitution or rerun was made. The 16 surviving pairs were analysed
exactly as registered.

| endpoint | plain | oneline | registered test | result |
|---|---:|---:|---|---|
| characters (primary) | 6,386 | 5,404 | two-sided exact paired permutation on task-level proportional deltas | p = 0.11292 |
| non-blank lines (secondary) | — | — | two-sided exact sign test: 8 smaller, 4 larger, 4 tied | p = 0.38770 |

The pooled character difference is -15.4%; the mean task-level proportional difference is
-8.7%. Neither changes the primary inference: the pre-registered threshold was p < 0.05.
The data therefore demonstrate no statistically significant solution-size effect for this
instruction on these tasks.

## Consequence fixed in advance

This is the second pre-registered minimal-change failure, and this task set is independently
authored and frozen. Per the protocol the claim is retired, in these words and no stronger:
**no statistically demonstrated effect on solution size under the tested protocol** — this
endpoint, this subset, this model, one draw per arm, size scored only where both arms
passed the gate. Non-significance is not equivalence: the 95% bootstrap CI on the mean
per-task proportional change is **[-18.3%, +0.9%]**, which is inconclusive against any
bound worth setting. The earlier exploratory 7-of-7 is superseded rather than promoted by
the directional pooled result here. No fourth endpoint or task-set rescue is planned.

Reproduce the analysis with:

```bash
python3 analyze_mbpp.py
```

The analyser validates that there are exactly 40 records for exactly the 20 tasks selected
from the hash-pinned source, rejects duplicate task/arm records, applies the registered
pairwise gate, and prints the registered tests.
