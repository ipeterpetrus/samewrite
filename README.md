# samewrite

Measure what a coding-agent session actually spends, then enforce the one rule that is
free to enforce.

`samewrite` came out of auditing real Claude Code transcripts — **1,316 of them,
237,541 assistant turns**. The headline finding is not the one people expect, and the
first edition of this repo got two of its three numbers wrong on a 24-transcript
sample. Those corrections are kept in the open in [docs/FINDINGS.md](docs/FINDINGS.md).

## The finding

Token volume across those transcripts:

| bucket | share of volume | share of price* |
|---|---|---|
| `cache_read` | **97.4%** | 68.8% |
| `cache_creation` | 2.2% | 19.7% |
| `output` | 0.3% | 11.5% |
| `input` | 0.0% | 0.0% |

\* cache-read 0.1x, cache-write 1.25x, output 5x the base input rate.

Anything entering the context at turn *i* is replayed on every turn after it. Cost is
**size × remaining turns**, and total session input grows **O(N²)**. What you write
once is cheap; what stays resident is not. So the question worth asking is not "who
generates the most tokens" but "who occupies the context the longest":

| source | share of carry |
|---|---|
| Bash call + result | **42.5%** |
| Read results | **21.3%** |
| injected banners — skill listing, hooks, reminders | **15.3%** |
| Write + Edit calls | 9.5% |
| assistant prose | 5.6% |
| human prompts | 4.2% |

Three consequences, each of which contradicts a popular piece of advice:

- **"Never rewrite a whole file, emit only the changed block."** Aimed at 9.5% of
  carry. Worse, the specific rule this repo used to ship — *≤3 change blocks, use an
  Edit* — is **net negative**: held out across 20 session-level splits it loses ~79% of
  the saving available, because one merged block can span most of a file. The feature
  that works is the **changed fraction**: under ~25% of the file changed → Edit; over
  ~40% → rewrite. That version keeps 84% of the oracle saving, and was never negative
  in 20 splits.
- **"Be terse to save tokens."** Assistant prose is 5.6% of carry. The *scaffolding*
  around the conversation is 15.3% — and the list of installed skills alone (median
  22.8 kB, injected at turn 0 and carried by every later turn) outweighs half of all
  prose. Uninstalling a plugin you do not use is a certain saving; being terser is a
  capped one.
- **"Add a skill for that."** Every always-on instruction block is itself carry.
  [§4 of FINDINGS](docs/FINDINGS.md#4-what-an-always-on-instruction-block-costs) derives
  the break-even — `N* = 2B / (f·s0)` — with measured B and s. This repo's own skill
  does not clear its cost on its edit rule alone; it clears it only by redirecting
  attention to Bash and Read.

## What one run finds

The hook is the small half of this repo. The measurement is the large half. Point
`tools/carry.py` and `tools/skills.py` at your own transcripts and you get a ranked
budget instead of folklore. Here is what one real setup returned — 421 sessions,
median 484 turns:

| what you are usually told | what was measured | what it is worth |
|---|---|---|
| "never rewrite a whole file, emit only the changed block" | Write+Edit calls are **9.5%** of carry — and the ≤3-block version of that rule is **net negative** | +0.072% once the rule is fixed |
| "be terse, output tokens are expensive" | assistant prose is **5.6%** of carry | ≤5.6%, paid for in clarity |
| *nobody mentions this one* | the skill listing is **30,009 bytes injected at turn 0**, and **66 of its 82 entries (72.9%) had never been invoked once** across 1,409 sessions | **~6,972 tokens re-sent on every single turn** — ~3% of session carry, recoverable with a settings flag |
| *nor this one* | `Read` results are **21.3%** of carry at a mean of **22.8 kB per call**, 25x a Bash result | read a range, not a file |
| "start a fresh session now and then" | correct — and it dominates everything else here | splitting a session in two measures **−41…−54%** |

Three of those five rows contradict the advice. The no-op guard this repo ships is the
smallest of them (0.077%) and the only one that needs no judgement — which is why it is
the only thing here that runs by itself.

```bash
git clone https://github.com/ipeterpetrus/samewrite && cd samewrite
python3 tools/carry.py  ~/.claude/projects/*/*.jsonl   # where your tokens actually are
python3 tools/skills.py ~/.claude/projects/*/*.jsonl   # what you carry and never invoke
```

Both read sizes, tool names and skill names only. No path, prompt, file content or tool
output is printed — and nothing is sent anywhere.

One thing survived every robustness cut: **20.8% of overwrites (154/741) wrote content
byte-identical to what was already on disk.** Zero changes, full token cost. That one
is free to fix, so `samewrite` ships a hook that fixes it.

## What's here

```
hooks/write_noop_guard.py   PreToolUse(Write) — deny writes identical to disk
hooks/install.sh            one command, idempotent, backs up settings.json
skills/edit-discipline/     when to anchor-edit vs rewrite whole (Claude Code skill)
tools/carry.py              carry by source over your own transcripts — the table above
tools/skills.py             price your skill listing: which entries you have never invoked
tools/extract.py            pull carry data out of transcripts (redacted by default)
tools/simulate.py           robustness suite: jackknife, bootstrap, holdout, drop-top-k
tools/report.py             read the field ledger: how often the guard fires, and how
                            many rewrites would have fit in an Edit
tools/feed.sh               regenerate docs/FIELD_DATA.md from the ledger, commit if changed
tools/health.py             is the guard still installed? ledger silence proves nothing on
                            its own, so compare it against session activity
tests/                      92 assertions in four suites, mutation-tested
docs/FINDINGS.md            full numbers, method, the corrections, and what an
                            adversarial panel broke before publication
```

## Status: experiment, not a default

An adversarial review panel held this back until the security boundaries and the
reproduction artifacts existed. They now do — but the honest framing survived the
review: this is an **optional experiment**, not a hook anyone should adopt by default.
Its load-bearing findings come from one author's sessions on one model family (August
2026). Measure your own before trusting it; every tool needed to do that is in here,
and [§8](docs/FINDINGS.md#8-what-would-falsify-this) says what result should make you
delete it.

## Install the hook

```bash
git clone https://github.com/ipeterpetrus/samewrite && cd samewrite
python3 tests/test_write_noop_guard.py     # 51 PASS expected
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

The retrospective number is 20.8% of overwrites. If your field rate lands under 2% over
a few hundred writes, the finding did not generalise — `report.py` says so itself, and
the right move is to remove the hook.

## Measure your own sessions

```bash
python3 tools/carry.py ~/.claude/projects/*/*.jsonl --markdown
python3 tools/skills.py ~/.claude/projects/*/*.jsonl --markdown
python3 tools/extract.py mine.pkl ~/.claude/projects/*/*.jsonl
python3 tools/simulate.py mine.pkl
```

`carry.py` and `skills.py` read sizes, tool names and skill names only — no path,
prompt, file content, or tool output is stored or printed.

`extract.py` is **redacted by default**: every line of every file is replaced with an
8-byte hash plus its token count, computed during extraction. That is enough for
`difflib` to find the same change blocks and enough to price them, while storing not one
character of your code. Paths, prompts, and tool output are never stored at all.

Redaction was not free to discover — the first version of this repo stored raw file
contents while the README claimed it did not. Re-running all 50 simulations on redacted
data moved the headline number by 0.001 pp (0.076% → 0.077%), so the privacy-preserving
path costs nothing in fidelity.

`--keep-content` turns redaction off for deeper analysis. Output then contains your file
contents verbatim. Do not share it.

## Security and support

The hook is code that runs on every `Write` in your session. Read it before installing —
it is 60 lines. It is **fail-open** on every error path, never writes, never sends
anything anywhere, and reads only the file the agent was about to overwrite.

Set `SAMEWRITE_ALLOW_NOOP=1` when an identical write is deliberate — refreshing mtime,
triggering a file watcher, testing idempotency.

Do not wire `git pull` into an auto-update for this hook. A hook that updates itself from
a remote repository is a code-execution path into your machine. Pin a commit, read the
diff, then update on purpose.

**Support: none promised.** This is a measurement result with tooling attached, published
because the negative findings are useful, not because it is a maintained product.

## Honest limits

- The saving is 0.077% (identical writes) plus at most 0.086% (an oracle edit policy;
  the deployable fraction rule reaches ~0.072% of that). Everything here is ~0.1%.
- The guard is **fail-open** on every error. It saves tokens; it does not prevent harm.
  A bug in it must never block real work.
- `PreToolUse` cannot see `@file` references (they enter context without a tool call),
  nor `cat > f` heredocs, `tee`, or `sed -i`. The skill covers those by instruction only.
- The changed-fraction rule is computed from the finished replacement, so an agent
  applies it as an estimate, not a measurement. Its sample is also 587 cases where the
  model had already chosen to Write.
- Byte-exact comparison on **raw bytes**. An earlier version read in text mode, which
  silently folds CRLF into LF — it would have blocked a legitimate line-ending
  normalisation. Found by cross-family audit, not by the test suite.
- Files whose path looks secret-bearing are skipped entirely. Not because the guard leaks
  contents — it never reads them out — but because deny/allow is an **equality oracle**:
  a caller could guess a file's contents and read the answer off the verdict.
- Session length dominates everything here. Literature puts compaction at −62.8…−85.9%;
  splitting a session in two measures at −41…−54% on this data. This repo is worth ~0.1%.
  Do not mistake it for the lever.

## License

MIT
