---
name: edit-discipline
description: Choose between an anchored Edit and a full rewrite when overwriting a file that already exists, and spend token discipline where a long session actually spends. Use before overwriting an existing file, or when session cost matters.
---

# Edit discipline

Measured on 1,316 Claude Code transcripts, 237,541 assistant turns (Aug 2026).
Cost is **carry** = size x turns remaining: the transcript is replayed as
cache-read input on every turn, so session input grows O(N^2). Producing a thing
is cheap. Leaving it resident is not.

## Overwriting a file that already exists

| condition | do |
|---|---|
| byte-identical to what is on disk | **do not write** — say it is already correct |
| under ~25% of the file changes | **anchored Edit** |
| over ~40% changes | **full rewrite**, and say why |
| 25-40% | either — take the one less likely to misapply |

**Changed fraction, not block count.** "<=3 change blocks -> Edit" is the rule
this repo shipped first; on the full corpus it *loses* ~79% of the available
saving, because one merged block can span most of a file. Held out across 20
session-level splits the fraction rule keeps 84% of the oracle saving (worst
split 75%) and was never negative. Edit is cheaper in 100% of cases under 5%
changed (n=31, 95% CI 89-100), 82% under 20%, 11% above 40%, 0% above 80%.

**20.8% of overwrites (154/741) were byte-identical to disk.** Free to skip.
Edit calls failed 6.2% of the time against Write's 12.2%, so anchoring is not
the riskier path.

## Where the tokens actually are

Shares below are the 421-session cohort; a later 1,080-file run put Bash at 45.1% and
Read at 19.8%, so quote a share together with the corpus it came from.

| source | share of carry |
|---|---|
| Bash call + result | 42.5% |
| Read results | 21.3% |
| injected banners (skill list, hooks, reminders) | 15.3% |
| Write + Edit calls | 9.5% |
| assistant prose | 5.6% |

Everything above the line is worth ~0.1% of a session. This half is worth more:
read a range, not a whole file (mean Read result 22.8 kB, 25x a Bash result);
ask Bash for the answer, not the log; and end the session — halving N halves
carry, which no rule on this page can do.

## How long the instruction itself should be

Two always-on instruction blocks were tested against one-sentence versions of their
own intent. The sentence won or tied every time; the kilobytes never won.

- **Terseness** — *"Answer tersely; keep every technical fact."* Cuts output tokens
  ~23% against no instruction (15 of 16 pairs, exact p = 0.0001), 100% of required
  facts retained. A 4,664-byte block saying the same thing measured **−0.8% against
  that one sentence** (p = 0.86) on a pre-registered run.
- **Minimal change** — *"Make the smallest possible change, add no unrequested
  abstraction."* Fewer non-blank lines in 7 of 7 pairs (p = 0.016). The 5,228-byte
  version: 5 of 7, p = 0.45.

Write the sentence, measure it, and only then consider a kilobyte of rules. That is
also why this file is 2 kB rather than 10.
