# Raw run records

Every scored run behind the exploratory rounds, one JSON object per run. Paths are
scrubbed (`/home/user`, `/tmp/rig`); nothing else is altered. The pre-registered
confirmatory run lives one directory up as `confirmatory_runs.jsonl` and its per-request
billing ledger as `confirmatory_ledger.jsonl` — those are the 48 runs the conclusions rest
on. What is here is the exploration that led to them, published so the path is auditable
rather than asserted.

Read these as exploratory. They were not pre-registered, the
fixtures changed between rounds, and two of the three generator hypotheses they suggested
were later killed by their own pre-registered thresholds. Treat a number that appears only
here as a lead, not a result.

| file | runs | fixtures/tasks | arms |
|---|---|---|---|
| `ab3.jsonl` | 12 | 1 | plain skill |
| `ab4.jsonl` | 24 | 3 | plain skill |
| `ab5.jsonl` | 12 | 1 | placebo plain skill |
| `ab6.jsonl` | 48 | 4 | placebo plain skill |
| `ab8.jsonl` | 36 | 4 | mode oneline plain |
| `ab_caveman.jsonl` | 36 | 4 | mode oneline plain |
| `ab_ponytail.jsonl` | 36 | 4 | mode oneline plain |
| `cal.jsonl` | 12 | 6 | plain |
| `quarantine/confirm.contaminated.jsonl` | 59 | 4 | mode oneline plain |
| `quarantine/ledger.contaminated.jsonl` | 595 | 4 | mode oneline plain |
| `pilot3.jsonl` | 18 | 6 | plain |
| `pilot4.jsonl` | 15 | 5 | plain |
| `pilot5.jsonl` | 18 | 6 | plain |
| `pilot6.jsonl` | 18 | 6 | plain |
| `results.jsonl` | 36 | 6 | plain skill |
| `results2.jsonl` | 54 | 6 | plain skill |
| `smoke.jsonl` | 2 | 1 | plain skill |
| `smoke2.jsonl` | 4 | 2 | plain skill |
| `smoke_cv.jsonl` | 8 | 4 | mode plain |

## quarantine/

Two files from a run that was launched twice by mistake; two rig processes wrote
overlapping `run_id`s to the same ledger. They are kept, not deleted, because deduping
them after the fact would be an unregistered exclusion — the honest record of the mistake
is the mistake. The run was relaunched once under a lock, and that clean relaunch is what
`confirmatory_runs.jsonl` contains. Nothing in `quarantine/` feeds any published number.
