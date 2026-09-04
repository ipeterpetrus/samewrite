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

Two always-on instruction blocks were tested against one-sentence versions of their own
intent. The sentence won or tied every time; the kilobytes never won.

**Terseness — replicated in two languages.** The instruction was measured as a prefix to
the request, against no instruction at all, on billed `output_tokens`, 16 pairs each,
exact paired permutation, two-sided:

| language | sentence as run | delta | lower in | p |
|---|---|---|---|---|
| Indonesian | `Jawab sesingkat mungkin, tanpa mengurangi isi teknisnya.` | **-22.7%** | 14/16 | 0.0001 |
| English | `Answer as briefly as possible, without reducing the technical content.` | **-19.6%** | 12/16 | 0.0070 |

The English run was pre-registered before it had data
(`experiments/skill-ab/PREREGISTRATION_english_replication.md`) and its prediction held.
The substance gate — a fixed list of facts each answer had to contain, with a negative
control proving it rejects empty and truncated answers — stayed at **100% in both arms of
both languages**, so the saving is not paid for in dropped content.

**What replicates is the direction, not the size.** The sentence was cheaper in **4 of 4
tasks in both languages**. The two magnitudes are not distinguishable: a post-hoc
interaction test gives +3.5 pp, p = 0.63. And four tasks is four observations however many
times each is repeated — a sign test across them bottoms out at p = 0.125, so treat this as
"it goes the same way in two unrelated languages", not as a measured size that transfers.

**Write the sentence in the language you actually prompt in.** Two languages is not all
languages, but the effect surviving a move between two unrelated ones is the evidence
that it is about instruction-following, not about a particular tokenizer. Translate the
sentence; do not import a foreign one.

**The kilobyte does not add anything.** A 4,664-byte always-on block saying the same thing
measured **-0.8% against the one sentence** (p = 0.86, Indonesian, pre-registered). Its
-23.4% headline is the block-versus-nothing contrast, and the sentence gets essentially
all of that on its own.

**Minimal change — one language only, and thinner.** *"Buat perubahan sekecil mungkin;
jangan menambah abstraksi yang tak diminta."* Fewer non-blank lines in 7 of 7 pairs
(p = 0.016) where a 5,228-byte version managed 5 of 7 (p = 0.45). This one has **no English
replication**, n = 7, and its endpoint is lines rather than tokens. Treat the English
rendering as untested.

**One channel was tested, and it is not this one.** Both sentences were delivered as a
prompt prefix, and the blocks as a `SessionStart` banner. Skill-body delivery — how you
are reading this — was never measured.

Write the sentence, measure it in your own language and channel, and only then consider a
kilobyte of rules. That is also why this file is under 5 kB rather than 10.
