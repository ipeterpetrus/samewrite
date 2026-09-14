# vNext benchmark — arms A–J in isolated config directories

Reproduces [docs/VNEXT.md §8](../../docs/VNEXT.md).

```bash
python3 selftest.py                                   # 51 checks, no model calls — run first
python3 rig.py --arms A,C,D --fixtures all --repeat 1 \
        --refs /path/to/clones --out runs/x.jsonl     # clones: ponytail/, i-have-adhd/ (arms E-J)
python3 analyze.py runs/x.jsonl --markdown
```

`rig.py` builds one `CLAUDE_CONFIG_DIR` per arm from nothing (settings + only that arm's
skill/hooks), copies the CLI credentials file into it (`cp`, never read) and deletes the copy
when done, runs `claude -p` in a temp dir outside every project tree, then scores mechanically:
target test + hidden neighbour test (build), file untouched + question asked (nochange), required
facts + shape contract (text). Treatment is verified from the transcript (`treatment_ok`): the
arm's banner/listing entry must be present and no foreign banner may be.

What it cannot see: the CLI injects its own built-in skill listing (~6.5 kB) and the account's
connector tool schemas in every arm, including A — a constant across arms, not zero.

Evidence classes for `runs/`: `pilot1.jsonl` = **pilot** (n = 1 per arm × fixture, pre-registered
contrasts, not analysis-eligible for a significance claim); `smoke.jsonl` = calibration only.
