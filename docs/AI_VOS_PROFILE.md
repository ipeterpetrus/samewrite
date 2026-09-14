# AI-VOS profile

A thin profile: how SameWrite's generic mechanisms line up with one governed multi-role operating
model. It adds no mechanism. Everything it uses — scopes, workload classes, evidence quality,
deterministic candidate ids, the exit-code contract — exists for anyone running more than one
agent, and nothing in `tools/` knows this file exists.

If you are not running AI-VOS, read [docs/MULTI_AGENT.md](MULTI_AGENT.md) and stop there.

**Source and scope of this document.** It was written against that system's own canonical
governance material, read directly, at a pinned revision. That material is private, so nothing
here reproduces its file paths, clause identifiers, revision hashes or wording; what follows is
only the mapping, stated in terms a reader outside that system can check against their own. Where
the two designs disagree, this document says so rather than smoothing it over.

## The correction that matters most

An earlier draft of this profile described AI-VOS as "one 24x7 multi-agent deployment" with roles
named builder, reviewer, ops and research, and told the operator to invent an agent label of their
own choosing. **Every part of that was wrong**, and the canonical material says so plainly:

| earlier draft claimed | what the canonical contract actually says |
|---|---|
| a fleet of agents running continuously | **one agent, one job** — a cross-agent orchestrator is an explicitly deferred phase, not current state |
| roles `builder / reviewer / ops / research` | the machine-enforced roles are **owner**, **model** and **agent**; in governance prose, **Owner**, **Maker**, **Reviewer** and a connector role |
| agent identity is the operator's free choice | **agent identity is an owner-approval item**, not something a tool or an operator may mint |
| a task class like build / audit / triage | the canonical task taxonomy is a **decision-risk class** with exact-match, no-ordering semantics |
| "no daemon is installed and none is needed" | that is true of SameWrite's own tooling; the governed system's **production plane is daemon-based and runs continuously** |
| a workload change is `WORKLOAD_SHIFT` | that system's verdict vocabulary is **pass / fail / not reached** |

The profile below is rewritten against the real contract. The mechanisms survived the correction;
the vocabulary did not.

## Two authority axes, and where SameWrite sits

The governed system separates **operational execution authority** (may this actor *do* this?) from
**decision authority** (how much independent model agreement does this *conclusion* need?). They are
orthogonal: a conclusion can require several independent models while its execution still requires
the owner. The default is the most restrictive level, and an unclassifiable case escalates rather
than proceeding — **default-deny, fail closed**.

SameWrite's observer and optimizer sit at the bottom of the first axis and the bottom of the
second, and they are built so they cannot climb either:

| SameWrite component | operational authority | decision authority |
|---|---|---|
| `tools/carry.py` (observer) | read-only observation | deterministic, zero model calls |
| `tools/optimize.py` (optimizer) | read-only observation, plus writing a proposal file into a state directory | deterministic, zero model calls |
| anything that changes `skills/` or `hooks/` | **not SameWrite** — a person, in a pull request | that system's own review contract |

This is the alignment that makes the profile work at all. In that system's ledger, model and agent
actors are **non-authority roles — never authority, however many agree**; only the owner role
carries authority. SameWrite's optimizer is exactly such an actor by construction: it emits a
proposal and holds `EXECUTION_AUTHORITY=NO`, `GIT_MUTATION_AUTHORITY=NO`,
`GITHUB_WRITE_AUTHORITY=NO`, `PROMOTION_AUTHORITY=NO`, `OWNER_AUTHORITY=NO`. It does not need to be
told to stay in its lane; there is no code path out of it, and `tests/test_multiagent.py` hashes the
policy tree around a run to prove the point.

## Mapping

| governed-system concept | SameWrite mechanism | honest note |
|---|---|---|
| Maker (patch / test / repair work) | `--scope-id maker` | one scope, not one scope per instance |
| Reviewer (read-heavy audit, separate model family) | `--scope-id reviewer` | the separation SameWrite can actually represent today |
| Owner (approval) | **not modelled** | the owner is not an agent whose transcripts are swept |
| operational authority level | `--workload-class` | opaque label only; SameWrite never interprets it |
| decision-risk class | **not modelled** | SameWrite has no notion of how many models agreed |
| evidence bundle | `evidence_run_ids` in the candidate specification | aggregate identifiers, never content |
| scheduled routine | cron or a systemd timer calling `tools/optimize.py` | SameWrite installs neither |
| proposal queue | `--emit-candidate <state dir>` | one directory per scope, outside any governed repository |

Two entries say **not modelled** on purpose. A profile that invented a representation for owner
approval or for decision-risk class would be building a second authority system inside a
measurement tool, and a second authority system is exactly the thing the governed system's
architecture forbids.

### Scope labels are constrained here, not free

Because agent identity in that system is an owner-approval item, a scope label must be **an existing
approved role name, used verbatim**, and never a new identity minted by whoever ran the command. The
per-instance form (`maker-07`) that `docs/MULTI_AGENT.md` offers generic users is **not** available
under this profile unless those instances already exist as approved identities.

### One divergence, stated rather than hidden

SameWrite's generic rule is that a scope label must not carry a hostname or a username, because the
label is written into a record that may be shared. The governed system does the opposite on purpose:
its evidence deliberately records the host a piece of work ran on, because host identity is part of
what an audit checks.

These are not reconcilable by argument, so the profile picks the stricter one and says why:
**keep hostnames out of the SameWrite scope label**, and let the audit trail record host identity
where it already does. SameWrite's record is an aggregate measurement that can travel; the audit
trail is a governed artifact that does not.

## Evidence rules, and the carve-out an earlier draft got wrong

That system's evidence doctrine and SameWrite's candidate invariant agree almost exactly: historical
evidence is append-only, raw artifacts are kept verbatim, and deleting canonical evidence is the
highest-restriction class — never autonomous. SameWrite's output-shaping candidates carry the same
rule in the specification file a builder actually reads.

But the earlier draft of that invariant was **incomplete in a way that could cause a leak**. It said
raw output must survive, with no exception — which would have preserved a credential verbatim and
called it an archive. The governed system carves secrets out explicitly, and SameWrite now does too:

> One carve-out, and it is not optional: secret material is never the evidence. A credential, key or
> token appearing in output is redacted at capture and never written verbatim into a retained
> artifact — preserving it is a leak wearing the word "evidence". Keep the finding, the location and
> the fact of exposure; never the value.

That sentence is in `tools/optimize.py` and in every candidate specification it emits, and
`tests/test_multiagent.py` fails if it goes missing. Reading the real contract is what found it.

## Models

The governed system treats **every model as a replaceable plug**, never part of its kernel, while
pinning specific lanes for specific work in execution, and requiring for higher-risk decisions that
the writer and the reviewer come from **different model families**.

SameWrite matches this by having no model at all. The observer and optimizer make zero model calls;
`tests/test_optimize.py` greps the source for model and network imports, and
`tests/test_multiagent.py` runs the whole tool with socket creation denied at runtime. There is
therefore nothing to pin, nothing to switch, and no way for a lane change to alter SameWrite's
behaviour.

Two consequences worth stating:

- **SameWrite never generates different runtime policy per model.** Evidence that differs by model
  is labelled `MODEL_SPECIFIC_SIGNAL` and may produce a candidate; it may not produce behaviour.
- **The writer-is-not-the-reviewer rule applies to SameWrite's own proposals.** A candidate written
  by this tool is not reviewed by it. That is the whole design, not a policy added on top.

## What this profile explicitly does not do

- It does not promote, merge, install, uninstall or modify anything.
- It does not add always-on text. The policy surface is byte-identical to the released `v1.1.0` tag.
- It does not add a network path, a model call, or a second telemetry channel.
- It does not give a fleet a shared brain. Each scope's evidence stays that scope's evidence.
- It does not claim that the governed system is multi-agent today. It is not. These mechanisms serve
  its existing maker-and-reviewer separation now, and its deferred multi-agent phase later.
