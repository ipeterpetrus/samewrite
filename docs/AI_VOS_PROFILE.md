# AI-VOS profile

A thin profile: how one 24x7 multi-agent deployment maps onto the generic contract in
`docs/MULTI_AGENT.md`. It adds no mechanism. Every mechanism it uses — scopes, workload classes,
evidence quality, deterministic candidate ids, the exit-code contract — exists for anyone running
more than one agent, and nothing in `tools/` knows this file exists.

If you are not running AI-VOS, read `docs/MULTI_AGENT.md` and stop there.

## Mapping

| AI-VOS concept | SameWrite mechanism | note |
|---|---|---|
| role (builder, reviewer, ops, research) | `--scope-id <role>` | one scope per role; never merged |
| agent instance | second component of the scope id, e.g. `builder-07` | opaque, your choice of granularity |
| task class (build, audit, triage) | `--workload-class` | a change here is `WORKLOAD_SHIFT`, not a regression |
| fleet-wide view | concatenate history files | safe in any order; `run_id` makes re-copying idempotent |
| orchestrator schedule | cron or your own loop calling `tools/optimize.py` | no daemon is installed and none is needed |
| proposal queue | `--emit-candidate <state dir>` | one directory per role, outside any governed repo |

## Role granularity: pick the coarsest that is still honest

A scope must be stable and low-cardinality. `builder` for a fleet of interchangeable builders is
better than `builder-07` if you never act on one instance's numbers, because a scope with four
records will sit at `INSUFFICIENT_DATA` forever. Use the per-instance form only when you intend to
compare instances.

Whatever you pick, the label is written verbatim into the record: it must not contain a hostname, a
username, a customer name, a project name, a ticket id, or anything else you would not publish.

## Why role isolation matters more here than anywhere else

The two findings the optimizer produces most often are exactly the two that are dangerous when
stated about a fleet instead of a role.

**Listing exposure.** "70 of 82 skill listing entries were never invoked" is true *for the scope
that was measured*. A reviewer role that never invokes a deployment skill is not evidence that the
ops role does not need it. The finding is labelled `SCOPE_LOCAL`, and the emitted specification
carries this invariant verbatim:

> Scope-local evidence. A listing entry cold in one role can be essential to another: this candidate
> is about reducing exposure IN THIS SCOPE, after proving no other role needs it. It is never an
> instruction to uninstall anything globally, and nothing is removed automatically.

**Output shaping.** "Bash output is 61% of carry" invites the rule "make Bash print less". For an
audit, a security review, a build validation or any failure path, the verbose output *is* the
evidence, and a rule that shortens it destroys the artifact the task exists to produce. Every
shaping candidate therefore carries:

> Never truncate the only copy of evidence. Raw output stays outside the model's context (host log,
> file, or the caller's own spool); the model receives a bounded digest; full detail stays
> retrievable on failure or on explicit request. For security, governance, build validation,
> destructive operations and any failure path, the raw record must survive.

Both invariants are in the candidate file itself, not only in documentation, because the file is
what a builder actually reads. `tests/test_multiagent.py` asserts both strings are present.

## A worked schedule

```bash
# each agent, at the end of its own run
python3 tools/carry.py --history "$STATE/carry_history.jsonl" \
        --scope-id "$ROLE" --workload-class "$TASK_CLASS" --max-files 500

# once an hour, per role, from cron — not a daemon
python3 tools/optimize.py --history "$STATE/carry_history.jsonl" \
        --scope-id "$ROLE" --accept-partial --strict-exit \
        --emit-candidate "$STATE/candidates/$ROLE"
case $? in
  0)  ;;                      # NO_ACTION — the expected outcome most cycles
  10) notify "candidate for $ROLE" ;;
  20|40) ;;                   # not enough evidence yet, or a bounded sweep; not an error
  41) ;;                      # another invocation holds the lock; skip this cycle
  *)  notify "optimizer status $?" ;;
esac
```

`--max-files 500` bounds the per-cycle cost to a fraction of a second regardless of how large the
archive grows, and marks the evidence `PARTIAL`; `--accept-partial` then says that the bounded
corpus is the intended target rather than a broken sweep. Drop both flags when you want the full
population and can afford the full sweep — 10,000 sessions cost about 12 seconds.

Point `--emit-candidate` at a state directory, never at a governed repository. The optimizer holds
no Git or GitHub authority and will not acquire any; a candidate reaches the codebase only when a
person opens a pull request.

## What this profile explicitly does not do

- It does not promote, merge, install, uninstall or modify anything.
- It does not add always-on text. The policy surface is byte-identical to the released `v1.1.0`
  tag, and no skill, hook or manifest references `tools/optimize.py`.
- It does not add a network path, a model call, or a second telemetry channel.
- It does not give the fleet a shared brain. Each scope's evidence stays that scope's evidence, and
  a finding never speaks for a role that was not measured.
