# Repository metadata — proposal only

`UPDATE_GITHUB_DESCRIPTION_REMOTE=NO` and `TOPICS_APPLIED=NO` for this task. Nothing here has been
applied to the remote; this file is the reviewable proposal, so the change is a decision rather
than a side effect of a release script.

## Description

**Current** (read from the API with `gh repo view --json description`, **196 characters**):

```text
Token-efficient skill for coding agents: reduce context, tool noise, needless edits and retries without sacrificing correctness — with private offline measurement and evidence-driven optimization.
```

It is accurate but it predates 1.3: it describes one host implicitly, and it spends its most
valuable characters on the measurement machinery rather than on what a reader gets.

**Proposed** (**147 characters**, measured, not estimated — inside GitHub's 350-character limit and
short enough to survive the search-result truncation that bites around 150–160):

```text
Token-efficient skill for coding agents — Claude Code, Codex, Hermes, OpenClaw. One canonical policy, one command per host. Measured, not promised.
```

The longer variant that also carries "losing results published" measures 173 characters and would
be truncated in a search listing, which costs more than the clause is worth. The clause stays where
it is already load-bearing: the README's first screen.

What changed and why:

| | |
|---|---|
| names the four hosts | the single largest fact a stranger needs in the first line, and the whole point of 1.3 |
| "one command per host" | the install friction is the adoption barrier, not the feature list |
| keeps "Measured, not promised" | the project's actual differentiator, in four words instead of a clause |
| drops "evidence-driven optimization" | jargon that costs 30 characters and says less than "measured" |

## Topics

Nineteen topics are already set. GitHub allows 20. Two hosts gained native support in 1.3 and are
not discoverable by topic:

| add | why |
|---|---|
| `codex` | native plugin support, verified by execution; the existing `hermes-agent` topic has no counterpart for Codex or OpenClaw |
| `openclaw` | same |

That is 21, one over the cap, so one has to go. **Proposed removal: `ab-testing`** — the weakest
of the nineteen. The experiments here are pre-registered arm comparisons, which `reproducible-research`
already covers, and nobody browsing `ab-testing` is looking for an agent skill.

Resulting set (20):

```text
agent-observability  agent-skills      agentic-coding    ai-agents
claude-code          claude-code-plugin claude-code-skills code-editing
coding-agents        codex             context-engineering developer-tools
hermes-agent         llm               llm-optimization   multi-agent
openclaw             prompt-engineering reproducible-research token-optimization
```

## Applying it

Not run here. When the owner decides to apply it:

```bash
gh repo edit ipeterpetrus/samewrite --description "Token-efficient skill for coding agents — Claude Code, Codex, Hermes, OpenClaw. One canonical policy, one command per host. Measured, not promised."
gh repo edit ipeterpetrus/samewrite --remove-topic ab-testing --add-topic codex --add-topic openclaw
```

Both are metadata-only and reversible; neither touches a tag, a release or a branch.
