# samewrite

Measure what a coding-agent session actually spends, then enforce the one rule that
is free to enforce.

`samewrite` came out of auditing 24 real Claude Code transcripts (29,838 assistant
turns). The headline finding is not the one people expect.

## The finding

Token accounting across those transcripts:

| bucket | share |
|---|---|
| `cache_read` | **98.6%** |
| `cache_creation` | 1.1% |
| `output` | 0.3% |
| `input` | 0.0% |

Anything entering the context at turn *i* is replayed as `cache_read` on every turn
after it. Cost is therefore **size × remaining turns**, and total session input grows
**O(N²)**. What you write once is cheap; what stays resident is not.

So the popular advice — "never rewrite a whole file, emit only the changed block" —
targets a rounding error. Measured across 50 simulations, enforcing it saves
**0.02–0.41% of session tokens**, and forcing *every* rewrite through anchored edits
is **+70% more expensive**, because scattered changes (6.9 change blocks per rewrite
on average) each carry their own anchor context.

One thing did survive scrutiny: **15% of overwrites wrote content byte-identical to
what was already on disk.** Zero changes, full token cost. That one is free to fix,
so `samewrite` ships a hook that fixes it.

## What's here

```
hooks/write_noop_guard.py   PreToolUse(Write) — deny writes identical to disk
hooks/install.sh            one command, idempotent, backs up settings.json
skills/edit-discipline/     when to anchor-edit vs rewrite whole (Claude Code skill)
tools/extract.py            pull carry data out of transcripts (redacted by default)
tools/simulate.py           50-simulation robustness suite: jackknife, bootstrap, holdout
tools/report.py             read the field ledger: how often it fires, and how many
                            rewrites changed <=3 blocks and would have fit in an Edit
tools/feed.sh               regenerate docs/FIELD_DATA.md from the ledger, commit if changed
tools/health.py             is the guard still installed? ledger silence proves nothing on
                            its own, so compare it against session activity; writes a run record
tests/                      57 assertions in two suites, mutation-tested
docs/FINDINGS.md            full numbers, method, and the limits of both
```

## Status: experiment, not a default

An adversarial review panel held this back until the security boundaries and the
reproduction artifacts existed. They now do — but the honest framing survived the
review: this is an **optional experiment**, not a hook anyone should adopt by default.
Its single load-bearing finding comes from one author's sessions on one model version
(August 2026). Measure your own before trusting it.

## Install the hook

```bash
git clone https://github.com/<you>/samewrite && cd samewrite
python3 tests/test_write_noop_guard.py     # 18 PASS expected
bash hooks/install.sh
```

Takes effect in the next session — `settings.json` is read at startup.

The installer wires an optional field ledger (`SAMEWRITE_LEDGER`, default
`~/logs/samewrite.jsonl`). It records **size and outcome only** — never a path, a
filename, or file content — so the claim in this README can be checked against what
actually happens rather than re-argued:

```bash
python3 tools/report.py ~/logs/samewrite.jsonl
python3 tools/report.py ~/logs/samewrite.jsonl --markdown > docs/FIELD_DATA.md
```

The retrospective number is 15% of overwrites. If your field rate lands under 2% over a
few hundred writes, the finding did not generalise — `report.py` says so itself, and the
right move is to remove the hook.

## Measure your own sessions

```bash
python3 tools/extract.py mine.pkl ~/.claude/projects/*/*.jsonl
python3 tools/simulate.py mine.pkl
```

`extract.py` is **redacted by default**: every line of every file is replaced with an
8-byte hash plus its token count, computed during extraction. That is enough for
`difflib` to find the same change blocks and enough to price them, while storing not
one character of your code. Paths, prompts, and tool output are never stored at all.

Redaction was not free to discover — the first version of this repo stored raw file
contents while the README claimed it did not. Re-running all 50 simulations on
redacted data moved the headline number by 0.001 pp (0.076% → 0.077%), so the
privacy-preserving path costs nothing in fidelity.

`--keep-content` turns redaction off for deeper analysis. Output then contains your
file contents verbatim. Do not share it.

## Security and support

The hook is code that runs on every `Write` in your session. Read it before installing
— it is 60 lines. It is **fail-open** on every error path, never writes, never sends
anything anywhere, and reads only the file the agent was about to overwrite.

Set `SAMEWRITE_ALLOW_NOOP=1` when an identical write is deliberate — refreshing mtime,
triggering a file watcher, testing idempotency.

Do not wire `git pull` into an auto-update for this hook. A hook that updates itself
from a remote repository is a code-execution path into your machine. Pin a commit,
read the diff, then update on purpose.

**Support: none promised.** This is a measurement result with tooling attached, published
because the negative findings are useful, not because it is a maintained product.

## Honest limits

- The 0.02–0.41% range is wide because one session supplied half the effect. Drop the
  five biggest contributors and it falls to 0.018%.
- The guard is **fail-open** on every error. It saves tokens; it does not prevent harm.
  A bug in it must never block real work.
- `PreToolUse` cannot see `@file` references (they enter context without a tool call),
  nor `cat > f` heredocs, `tee`, or `sed -i`. The skill covers those by instruction only.
- Byte-exact comparison on **raw bytes**. An earlier version read in text mode, which
  silently folds CRLF into LF — it would have blocked a legitimate line-ending
  normalisation. Found by cross-family audit, not by the test suite.
- Files whose path looks secret-bearing are skipped entirely. Not because the guard
  leaks contents — it never reads them out — but because deny/allow is an **equality
  oracle**: a caller could guess a file's contents and read the answer off the verdict.
- Session length dominates everything here. Literature puts compaction at −62.8…−85.9%.
  This repo is worth ~0.1%. Do not mistake it for the lever.

## License

MIT
