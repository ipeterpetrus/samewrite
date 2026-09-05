---
name: edit-discipline
description: Choose between an anchored Edit and a full rewrite when overwriting a file that already exists, and spend token discipline where a long session actually spends. Use before overwriting an existing file, or when session cost matters.
---

# Edit discipline

Measured on 1,316 Claude Code transcripts, 237,541 assistant turns (Aug 2026). Cost is
**carry** = size x turns remaining: the transcript is replayed as cache-read input on every
turn, so session input grows O(N^2). Producing a thing is cheap. Leaving it resident is not.

## Overwriting a file that already exists

| condition | do |
|---|---|
| byte-identical to what is on disk | **do not write** — say it is already correct |
| under ~25% of the file changes | **anchored Edit** |
| over ~40% changes | **full rewrite**, and say why |
| 25-40% | either — take the one less likely to misapply |

**Changed fraction, not block count.** "<=3 change blocks -> Edit" loses ~79% of the
available saving on the full corpus, because one merged block can span most of a file; the
fraction rule keeps 84% of it held out over 20 session-level splits and was never negative.
**20.8% of overwrites were byte-identical to disk** — free to skip. Edit calls failed 6.2%
of the time against Write's 12.2%, so anchoring is not the riskier path.

## Where the tokens actually are

421-session cohort; a later 1,080-file run put Bash at 45.1% and Read at 19.8%, so quote a
share with its corpus. `tools/carry.py` prints attachments per type; this table sums them.

| source | share of carry |
|---|---|
| Bash call + result | 42.5% |
| Read results | 21.3% |
| injected banners (skill list, hooks, reminders) | 15.3% |
| Write + Edit calls | 9.5% |
| assistant prose | 5.6% |
| human prompts | 4.2% |
| other tools | 1.5% |

Everything in the section above is worth ~0.1% of a session. This half is worth more:
read a range, not a whole file (mean Read result 22.8 kB, 25x a Bash result); ask Bash for
the answer, not the log; and end the session — halving N halves carry, which no rule on
this page can do.

## The instruction itself

Prefix the request with **one sentence, in the language you actually prompt in**. Measured
against no instruction, on billed output tokens, 16 pairs each, facts retained 100%:
`Jawab sesingkat mungkin, tanpa mengurangi isi teknisnya.` **−22.7%** (14/16, p = 0.0001);
`Answer as briefly as possible, without reducing the technical content.` **−19.6%** (12/16,
p = 0.0070, pre-registered). A 4,664-character always-on block saying the same thing added
**−0.8%** over the sentence (p = 0.86). Do not ship the block.

The minimal-change sentence ("make the change as small as possible; add no unrequested
abstraction") failed two pre-registered tests; no number is quoted for it. Sentences were
measured as a prompt prefix, blocks as a `SessionStart` banner — never as a skill body like
this one. Protocols, intervals and every retraction: `docs/FINDINGS.md` section 9.
