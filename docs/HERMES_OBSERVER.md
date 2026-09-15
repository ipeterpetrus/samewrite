# Hermes observer — deferred by scope

```text
HERMES_SKILL    = VERIFIED
HERMES_OBSERVER = DEFERRED_BY_SCOPE
```

This is a decision, not an unfinished task. SameWrite's skill works on Hermes Agent and is verified
there. What is deferred is the *observer* — the offline reader that turns a host's own session
records into aggregate cost evidence.

## Why defer

1.3 is about portable core skill and install compatibility across four hosts. An observer for
Hermes would require SameWrite to depend on the shape of another project's private session store —
a table layout free to change in any release, in a project whose default branch moved twice during
this cycle and was force-pushed once. That is long-term coupling bought for a capability no current
user has asked for.

The honest form of the trade: SameWrite would gain a number, and take on a maintenance obligation
to a schema it does not control and cannot pin.

## What was established, so future work does not start cold

Audited at `NousResearch/hermes-agent`, branch `437116f`, release `v2026.9.14` / package `0.21.3`.

| question | answer |
|---|---|
| where do sessions live? | **SQLite** at `$HERMES_HOME/state.db` — *not* the `sessions/` directory, which holds only a routing index, emergency diverted transcripts and debug dumps |
| is per-tool aggregation possible? | **yes** — the messages table carries a tool name, a timestamp and a token count per row |
| can it be done without reading content? | **yes** — a `COUNT(*)` and `SUM(LENGTH(content))` grouped by tool name returns only integers; the length is computed inside the engine and the content column is never selected |
| is anything lossy? | **yes** — an oversized tool result is replaced by a preview *before* it reaches the database, so pre-truncation sizes survive only as prose inside the stored text. A content-free reader can detect those rows and report a lower bound, not a true total |
| is stored content sensitive? | **yes** — prompts, model output, tool arguments and tool results are stored in plaintext. Any reader must open the database read-only and must never place the content or tool-call columns in a select list |

## What a future implementation must satisfy before it ships

Not a wish list — these are the gates, and a parser that misses any of them is not shippable:

```text
read-only database handle              open with a read-only URI, never a writable handle
schema version pinned and asserted     unknown schema -> UNSUPPORTED_SCHEMA, never guessed parsing
zero text-content read                 no content column, no tool-call column, in any select list
privacy canary test                    a planted secret absent from history, JSON, specs and logs
zero network, zero model calls
fail closed on drift                   a changed table is a refusal, not a best-effort parse
```

Until every one of those is met the label stays `DEFERRED_BY_SCOPE`. A partial parser is not
labelled `VERIFIED` here, and a table cell is never made greener than the evidence behind it.

## What this does not mean

It does not mean the observer cannot be built; the audit above says it can. It does not mean Hermes
support is incomplete — the skill is verified, which is the thing a Hermes user installs. And it is
not a failure: declining to couple to another project's private storage for a capability nobody has
asked for is the same discipline that rejected `bash-output-shaping` and the truth rule.
