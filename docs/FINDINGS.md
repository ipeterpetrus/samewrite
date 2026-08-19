# Findings

Basis: 24 Claude Code transcripts, 29,838 assistant turns, 122 overwrites of files the
session had written itself. Tokenizer: `o200k_base` (tiktoken), not a chars/N estimate.

## 1. Where the tokens actually go

| bucket | tokens | share |
|---|---|---|
| cache_read | 1,122,280,007 | 98.6% |
| cache_creation | 12,360,805 | 1.1% |
| output | 3,593,178 | 0.3% |
| input | 5,858 | 0.0% |

Weighted by price (cache_read ×0.1, cache_write ×1.25, output ×5): cache_read 77%,
output 12%, cache_write 11%.

Carry per source in a 1,434-turn session — `size × remaining turns`:

| source | share of carry |
|---|---|
| Bash results | 32.5% |
| Write calls | 25.4% |
| Bash calls | 18.4% |
| prose | 6.0% |
| Edit calls | 4.0% |
| Read results | 1.3% |

Bash dominates by **volume**, not fat: 74% of tool calls, 51% of carry — a ratio of
0.7×, i.e. leaner than average. Write is 10% of calls and 25.4% of carry: **2.5×
over-represented**. That is where a rule can bite.

## 2. The counterfactual

Replacing every overwrite with anchored edits costs **217,950 tokens vs 127,864** for
the writes themselves — **+70%**. Only **43%** of overwrites are cheaper as edits.
Average change blocks per overwrite: **6.9**.

Robustness across 50 unique simulations:

| method | n | range |
|---|---|---|
| bootstrap (resample sessions) | 14 | 0.017–0.294%, median 0.108% |
| jackknife (drop one session) | 15 | 0.089–0.195% |
| holdout (random half) | 6 | 0.021–0.411% |
| drop top-k contributors | 5 | 0.067% (k=2) → 0.018% (k=6) |

**These are 50 unique configurations, not 50 independent observations.** Jackknife,
bootstrap and holdout all resample the *same* 24 sessions, so the spread describes
sensitivity to sample composition — not a sampling distribution. No confidence interval
is claimed here, and none should be read into it.

**The estimate is not stable.** One session (`dfd5d8d3`) supplies half the effect:
removing it takes 0.176% → 0.089%. Twelve of 24 sessions contribute nothing at all.

At real prices, the total modelled saving over all 24 sessions is **$35.08** (Opus
cache-read rate), **$7.02** (Sonnet), **$1.87** (Haiku).

## 3. The part that holds

**18 of 122 overwrites (15%) wrote byte-identical content.** 11,923 output tokens,
10,083,748 carry tokens, **0.076%** — larger than the best realistic edit-policy
result (0.030%) and with **no trade-off at all**, because the operation was never
needed. Largest single case: 133 lines, 1,797 tokens, zero changes.

This is the only finding that survives every robustness cut, and the only one that can
be enforced mechanically at zero carry cost.

## 4. External evidence

aider's own benchmark data (`aider/website/_data/*.yml`), same model tested in two
formats:

| model | format | pass % | well-formed % | malformed |
|---|---|---|---|---|
| gemini-exp-1206 | diff | 69.2 | 84.2 | 68 |
| | whole | **80.5** | **100.0** | **0** |
| llama-3.1-405b | diff | 63.9 | 92.5 | 19 |
| | whole | **66.2** | **100.0** | **0** |
| o1-mini | diff | 61.1 | 100.0 | 0 |
| | whole | **70.7** | 90.0 | 0 |
| qwen2.5-coder-32b | diff | 8.0 | 71.6 | 148 |
| | whole | **16.4** | **99.6** | 1 |
| gpt-4-turbo | diff | 57.6 | 100.0 | 0 |
| | udiff | **63.9** | 97.0 | 4 |

Whole-file beats diff on pass-rate in **4 of 6** pairs. Diff is not a free win — it
trades output tokens for apply-failure risk. aider also disables its own fuzzy matcher
(`editblock_coder.py`: an unconditional `return` before `replace_closest_edit_distance`).

aider has **no no-op write guard** — checked, no hits for content-equality in
`coders/` or `io.py`. The gap this repo closes is not covered upstream.

## 5. What this does not fix

Total input grows O(N²) because the transcript is replayed each turn. Measured on real
data, splitting a session in two cuts carry to **46.5–59.3%** (uniform-split prediction:
50%); into four, **23.8–39.1%**. Published work on compact memory reports −62.8…−85.9%.

Everything in this repo is worth ~0.1%. Session length is worth 50–88%.


## 6. What would falsify this

- Re-run `tools/extract.py` + `tools/simulate.py` on your own transcripts. If no-op
  overwrites are under 2% of overwrites, the one finding this repo rests on does not
  generalise beyond the author's sessions and model version (August 2026).
- Install the hook and count denials. Zero denials over a month of real work means the
  behaviour was model-version-specific and the hook is dead weight — remove it.
- The guard is advisory and racy by construction: it reads the file, then the host
  performs the write. Anything that mutates the file in between is outside its
  knowledge. It cannot be made race-free without owning the write itself.
