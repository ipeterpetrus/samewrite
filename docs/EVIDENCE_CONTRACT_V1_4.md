# SameWrite v1.4 — evidence contract, simplified generation

`OWNER_DECISION=SIMPLIFY_EVIDENCE_OPTIMIZER_SURFACE`

This is the successor freeze. It inherits `phase1s/EVIDENCE_CONTRACT_1S.md` in full EXCEPT for
the sections restated below. Where this document and the predecessor disagree, this document
governs; where it is silent, the predecessor governs unchanged. The predecessor freezes are not
overwritten: `EVIDENCE_CONTRACT.md` (phase 1), `phase1r`'s and `phase1s`'s remain exactly as they
were, and the lineage with their hashes is in `LINEAGE.md`.

## §2a REPLACED — the analysis population

There is no temporal window. An analysis is evaluated over a **population**: the validated
observations a container holds for one scope and one workload class, in canonical order
(position, then record digest), carrying an identity computed over what those members say.

```
Population = (scope, workload, members, identity)
population_for(container, scope, workload) -> Population
```

Normative:

1. **The kernel selects no evidence by time.** There is no horizon, no cutoff, no "newest N", no
   `since` and no `lookback` in the evidence-decision kernel, under any name.
2. **A population is deterministic and identified.** Two readers of the same file produce the
   same members in the same order and the same `population_id`; a reader of different evidence
   produces a different one. The identity covers both position and content, so a record replaced
   at the same position is a different population.
3. **A population may be empty.** An empty population is a fact about the evidence, not an error
   and not an absence.
4. **A smaller population is an ACQUISITION decision, not a kernel one.** A caller that wants
   less evidence acquires less evidence; the acquisition certificate then records `sample_policy`,
   `sample_bound` and the frozen selection, the observation derives `BOUNDED`, and §2's promotion
   gate requires the operator to accept that bound explicitly. This is the only supported way to
   analyse part of a history.

## §2b REPLACED — container integrity is global

> A container's integrity is determined from the complete validated container evidence available
> to the kernel, independent of the analysis population selected for any particular finding.

Normative:

1. `history_integrity(container, head, scope, now, head_required, quarantine_file, archives)`
   takes **no** population and **no** window. One container, one integrity, one answer.
2. Every fault it finds changes the state: an unparseable line, a record of an unreadable
   generation, a semantically invalid observation, a duplicate position, a dedup conflict, a
   broken chain, a restore floor, a head that is stale, missing-when-required or unreadable, and
   a quarantine binding that cannot be shown. The previous generation reported some of these as
   reasons without changing the state when they fell outside the window; that distinction is
   gone.
3. Container truth and the analysis population are **separate inputs** to a finding. A degraded
   container with a valid population is a normal, expressible state; neither hides the other.
4. A line that did not decode has no position and no scope, so it belongs to the container.

## §9a/§9b REPLACED — the run status, without host-shift

`HOST_BEHAVIOR_SHIFT` and `IneligibleReason.HOST_SHIFT` are removed; **exit code 30 is retired
and not reused**. Invariant I4 (a live-sweep-only finding cannot span two hosts) is removed with
the mechanism it policed. The remaining invariants I1, I2, I3, I6 and I7 are unchanged.

Host identity remains where it always was — in the acquisition certificate, the ledger
certificate and the world identity — as a **comparability** fact: it says whether two
observations can be compared. It is no longer a temporal detector.

## §3b AMENDED — sufficiency facts

`window_truncated_by_rotation` becomes `population_truncated_by_rotation`, with the same meaning
for the new subject: evidence that should have been in the population was rotated out of the
active file. The floors themselves are unchanged.

## Appendix B.1 REPLACED — the finding registry

Entries carry no `horizon_days`. Each retained finding declares its dependency contract, and the
registry refuses to import if any part of it is missing or could never be evaluated:

```
consumes                which evidence components it reads
requires_container      the container integrity it needs
requires_acquisition    the acquisition states that can support it (INTACT, or BOUNDED accepted)
requires_sufficiency    SUFFICIENT
comparability           the dimensions two observations must share (scope, workload, world)
floors                  min_sessions, min_turns, min_history_for_trend, min_ledger_*
```

Retained: `listing_cost`, `write_guard_retirement`.
Removed: `carry_bytes_trend` and `carry_share_concentration` — each named in `REMOVED_FINDINGS`
with its reason, and refused by name by both `floors_for` and `make_finding_id`.

`carry_share_concentration` was cut because it was the only retained finding that AGGREGATED
across the observations of a population: its validity needed those observations to be comparable,
and with host-shift removed nothing establishes that two observations from different hosts are.
The Owner cut the finding rather than add a host-comparability mechanism to preserve it. Every
retained finding now rests on ONE observation (a live sweep) or ONE certificate (the ledger), so
"the same host" has no referent for either of them. No retained entry consumes `history`.

`min_history_for_trend` is a COUNT of comparable observations in the population. It is not a time
span, the registry refuses an entry that imposes it without consuming history, and no retained
entry imposes it.

## Record vocabulary

Six kinds: `carry_sweep`, `carry_sweep_failed`, `history_quarantine`, `history_quarantine_lost`,
`history_rotated`, `history_restored`. `host_rebaseline` is removed. A current-generation line
carrying it is REFUSED (`record_unknown_type`), counted as unreadable, and therefore keeps the
container from being INTACT; a legacy-generation line carrying it reads as a legacy record of
unverified kind. No file is rewritten and nothing is deleted.

## Machine output

Removing a member from the `status` closed enum NARROWS its domain, which the contract's own
schema-evolution policy classifies as requiring a version bump (`narrowed_domain:status`). The
v1.4 output schema version must therefore carry this change; it is not a compatible addition.
No removed field is kept as a cosmetic placeholder.

## Host identity

`host_profile_id` is carried on the acquisition certificate and the ledger certificate as
PROVENANCE and diagnostic attribution. It is not part of `world_id_core`, `world_id`, `sample_id`
or any comparability gate, and no kernel decision reads it. A population identity distinguishes
observations that differ in host only because it digests what each member SAYS — which is
provenance, not a comparability rule.

## §2 AMENDED — the promotion gate reads the finding's contract

```
promotable(finding, acquisition_integrity, container_integrity, sufficiency, accept_bounded,
           world_state, freshness_ok)
```

Normative: a finding is promotable only when the container it rests on is no worse than its
declared `requires_container`, its acquisition state is one the contract accepts (BOUNDED only
with explicit operator acceptance), its sufficiency is what the contract requires, the world is
single where the contract declares that dimension, and the newest measurement is itself
promotable. A declaration in the registry that the gate does not read is not part of this
contract; there are none.

## Unchanged

Two axes (`AcquisitionIntegrity` × `AnalysisSufficiency`) and their vocabulary, BOUNDED vs
DEGRADED, the promotion gate (minus its host-shift argument), closed nominal types, single
construction authority, the wire parser reading shape only, canonical JSON, the absence triple,
dedup with its canonical representative, the artifact/world binding, the transaction protocol,
the legacy reader, and the full reason vocabulary.
