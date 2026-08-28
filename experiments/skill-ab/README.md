# skill A/B: what does invoking a process skill cost, and does it change the outcome?

Reproduces [§9 of FINDINGS](../../docs/FINDINGS.md#9-what-an-always-on-skill-costs-measured-twice).

Two arms over the same bug fixtures, one sentence apart. Scoring is mechanical — a NEIGHBOR
test that never exists in the working directory while the agent runs catches symptom-only
fixes — so no LLM judges the result:

| verdict | meaning |
|---|---|
| `FAIL` | target test still red |
| `SYMPTOM` | target green, neighbour red — the fix treated the symptom |
| `ROOT` | both green |
| `INVALID` | the agent edited a test file |

```bash
python3 -c "import fixtures_round2 as f, subprocess, tempfile, os   # positive control first
..."                                     # see FINDINGS §9: apply the golden fix, expect ROOT
python3 run.py --repeat 3                # 6 fixtures x 2 arms x 3 repeats
python3 analyze.py results2.jsonl        # outcome table + per-fixture sign test
python3 price.py  results2.jsonl minicfg/projects   # rate-card translation
```

`run.py` points `CLAUDE_CONFIG_DIR` at a minimal config holding only the skill under test,
so the measurement is not diluted by whatever preamble and hooks the host session carries.
It deliberately does not delete its working directories: the diff the agent wrote is the
evidence.

Three things this design gets right and most skill "evaluations" do not, and one it does
not: the treatment is **verified** (every skill-arm transcript must contain a `Skill` tool
call, every plain-arm transcript must not), the rubric is proven **reachable** by a golden
fix before any agent runs, and the scoring needs no judge. What it does not get right: both
fixture sets were written by the same author, the second after seeing the first hit a
ceiling — they are two attempts, not two independent replications.
