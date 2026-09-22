# SameWrite 1.4.2 — release notes

**One sentence.** v1.4.2 hardens the legacy optimizer's evidence integrity and keeps candidate
emission inside the requested output root, while leaving the SameWrite skill body, routing
description and hook behaviour unchanged.

This is a **patch** release. **The skill body is byte-identical**, its description is unchanged,
no hook behaviour changed, and nothing new is activated. Nothing a model reads changes; what
changes is how the offline optimizer (`tools/optimize.py`) weighs legacy evidence and where it is
allowed to write a candidate specification. It ships two merged pull requests:
[#13](https://github.com/ipeterpetrus/samewrite/pull/13) (evidence integrity) and
[#16](https://github.com/ipeterpetrus/samewrite/pull/16) (candidate-path containment, closing
[#15](https://github.com/ipeterpetrus/samewrite/issues/15)). Both were accepted by an independent
review before merge.

## 1. What was wrong

- **The legacy optimizer promoted findings from evidence it never checked.** Six defects were
  reproduced on `77e3677` before anything was repaired (`docs/V142_COUNTEREXAMPLES.md` §1–§2):
  * a history built from bounded sweeps promoted a candidate, and `--accept-partial` changed
    nothing because it was never read;
  * one newer ineligible record anchored the analysis and stranded six eligible ones;
  * `HOST_BEHAVIOR_SHIFT` refused promotion while still writing the candidate file;
  * a record claiming `COMPLETE` with zero sessions, turns and carry promoted;
  * a live sweep that lost a torn transcript line reported `COMPLETE`;
  * the carry sweep and the skill-listing scan selected different "newest N" transcripts.
- **Candidate emission could leave the operator's output root.** The candidate id carries the
  analysed scope verbatim and was also used as the directory name, so a scope such as
  `x/../../up` put `HYPOTHESIS.md` above the `--emit-candidate` directory. A NUL in a legacy
  scope ended in a Python traceback with no `--json` result, and a symlink already sitting at the
  candidate's directory name was followed out of the root (#15).

## 2. What changed — legacy evidence integrity (PR #13)

- **Evidence quality is derived, not trusted.** One place decides what a legacy record is worth:
  the worst of what it claims and what its own counters prove. A `COMPLETE` claim with impossible
  numbers (zero sessions with files scanned, sessions without turns, carry without shares, more
  sessions than files scanned) is `INVALID`. A schema older than the quality field, or a schema-2
  record without the acquisition counters its writer always wrote, is `UNKNOWN`.
- **An intentional bound is not a loss.** `PARTIAL` means a bound the caller chose
  (`skipped_by_limit`). `DEGRADED` means evidence that was selected and then lost (unreadable,
  oversize, malformed, identity changed under the read, conflicting sources). The live sweep
  derives the same distinction from its counters.
- **`--accept-partial` adopts an intentional bounded corpus, and nothing else.** It never adopts
  `DEGRADED`, `UNKNOWN`, `INVALID` or `EMPTY` evidence.
- **Lost evidence no longer reads as complete.** A torn or malformed transcript line makes the
  live sweep `DEGRADED`, and the run reports `PARTIAL_EVIDENCE` instead of `NO_ACTION`.
- **Eligibility comes before anchoring.** The newest record that can speak for a population
  chooses the scope, workload class and corpus size. An `INVALID` or `EMPTY` record no longer
  strands the eligible history behind it.
- **A refusing status writes nothing.** The status gate lives inside `emit_candidates()`, so no
  caller can persist a specification under `HOST_BEHAVIOR_SHIFT`, `PARTIAL_EVIDENCE`,
  `INSUFFICIENT_DATA` or `NO_ACTION`. A run that promised a candidate and wrote none reports
  `INTERNAL_ERROR`.
- **One definition of a bounded sample.** `carry.bounded_paths()` selects the newest N sources
  once; the carry sweep and the listing scan receive the same selection.
- **Physical loss opens a recoverable history epoch, not permanent poisoning.** A rejected line
  cuts the history at its position. Evidence before the cut is never combined with evidence after
  it, and enough clean later evidence promotes normally. The damage stays reported in
  `history.damage`.
- **A rejected record is not trusted for its own scope.** A line that failed validation cuts
  every scope (`file_global`). It can never name the population it damaged, and a line that is
  not valid UTF-8 is a loss, not a label. `scope_id` itself is validated before a record is
  accepted.
- **A valid record whose own counters prove a loss opens a trusted scope-local boundary.** It
  belongs to the epoch it closes; other scopes are not cut.
- **A `run_id` is an identity claim, not proof.** Two records are one run only when their scope,
  file-global epoch, `run_id` **and** canonical persisted observation all match (`TRUE_RETRY`):
  deduplicated and counted, opening no boundary. The same identity with a different observation
  is a `RUN_ID_CONFLICT`: counted in `history.run_id_conflicts`, never reported as a retry, and
  it cuts a scope-local boundary that later evidence recovers from.
- **Zero carry is legitimate evidence.** A sweep that measured no carry (`shares: {}`,
  `carry_bytes: 0`) is readable and `EMPTY`, not corruption.
- **Legacy optimizer `--json` output schema is now v2.** It adds `history.quality`,
  `history.damage`, `history.run_id_conflicts` and `scope.records_in_epoch`, and removes no key.
  `evidence_quality` is now derived and may read `DEGRADED` or `UNKNOWN`. A `CANDIDATE` whose own
  evidence passed its gate now outranks `PARTIAL_EVIDENCE` from evidence it never used.

## 3. What changed — candidate-path containment (PR #16, closes #15)

- **Logical identity and storage identity are separate values.** `candidate_id` stays the
  logical identity, scope included, and is never rewritten. `candidate_storage_component()` is the
  single mapping from that id to a directory name.
- **Ordinary candidate directories keep their names.** An id that is already one ordinary path
  component is its own directory name, byte for byte, so existing candidates are still found.
- **Unsafe ids are re-homed deterministically.** An id holding `/` or `\`, equal to `.`, `..` or
  empty, or starting with the reserved prefix under upper-casing, is stored as
  `candidate-sha256-<sha256 of the complete id>`: one component, deterministic, never a dot
  segment.
- **Candidate-controlled identity cannot leave the resolved `--emit-candidate` root.** The emitter
  checks, whatever the caller hands it, that the candidate directory is a direct child of
  `realpath(OUTDIR)` (path semantics, not a string prefix). Checked on the legacy-history scope
  surface and on `--scope-id`, and with relative, `..`-spelled and symlinked output roots.
- **A pre-existing symlink at the candidate directory name is refused**, not followed; so is a
  Windows junction where the interpreter can detect one (Python 3.12+).
- **NUL and pathname-invalid identities fail through a controlled machine result.** They are not
  hashed into a name. The run prints its `--json`, reports the logical id in `candidates_failed`
  with a static reason, reports `INTERNAL_ERROR` when nothing else was written, and leaves no
  traceback, no temporary file and no lock.
- **Machine fields still report logical ids.** `candidate_ids`, `candidates_written`,
  `candidates_existing` and `candidates_failed` are unchanged in meaning, and `HYPOTHESIS.md` still
  states the logical `candidate_id` and `scope_id`. No output field was added for this.
- **Issue #15 is closed.**

## 4. What did NOT change

```text
canonical skill body ................. unchanged
skill description .................... unchanged
hook behavior ........................ unchanged
routing behavior ..................... unchanged
automatic promotion .................. NO
automatic candidate persistence ...... NO
automatic policy mutation ............ NO
schema-4 legacy-optimizer support .... NO
AI-VOS activation .................... none
new model-facing instructions ........ none
```

```text
TOTAL_SAVINGS ................... NOT_PROVEN
WORLD_BEST_CLAIM ................ NOT_TESTED
```

The version bump activates nothing. `tests/test_release_shadow_only.py` proves that
mechanically: no promotion entry point ships, the shadow reporter creates no file and no
candidate, and no runtime module branches on the product version. The legacy optimizer still
refuses current-generation (schema-4) records by name.

## 5. Known open maintenance debt

These are tracked separately. Neither was introduced by 1.4.2, and neither is repaired here.

- **#14.** A legacy record with a non-string `run_id` can crash candidate rendering and may leave
  a temporary candidate file behind.
- **#17.** Under the current trust model, a co-writer that already has write access inside a
  candidate directory can pre-place the predictable candidate temporary pathname
  (`HYPOTHESIS.md.tmp-<pid>`) as a symlink, which the write then follows. This needs another
  actor or process that already has write access inside the candidate directory. It is not
  remote access, code execution or privilege escalation.

## 6. Other disclosed residuals

- **Legacy `UNKNOWN` evidence stays fail-closed.** It cannot promote, `--accept-partial` does not
  adopt it, and it opens no epoch. An `UNKNOWN` record in the active epoch of a scope therefore
  keeps history-based promotion refused for that scope.
- **Check-then-create race.** The containment check and the directory creation are two system
  calls. A separate actor that can already write inside the output root could swap a link in
  between.
- **Case-insensitive volumes are modelled, not measured.** The reserved-prefix rule uses
  upper-casing as the model of NTFS and macOS name comparison; it can only over-match. It has not
  been executed on a real case-insensitive filesystem in CI.
- **Windows junctions on Python below 3.12** are not detected, and Windows paths remain
  `UNTESTED`, as the README already states.
- **A scope holding a lone UTF-16 surrogate** still fails earlier, in the candidate id's own
  digest. That is pre-existing and outside the path repair.

## 7. Compatibility

- **Drop-in patch.** No skill body change, so no model-facing behaviour changes, and no model
  benchmark is re-run for this release.
- **Evidence history.** Schema 4 is unchanged. For the same input, the records the producer
  writes are byte-identical to 1.4.1's except for the writer-version field, which now reads
  `1.4.2`. Legacy histories (schemas 0–2) are read by the stricter law above.
- **The optimizer can say no where 1.4.1 said yes.** A history containing bounded, lost,
  unattested or impossible evidence can now report `PARTIAL_EVIDENCE` or `INSUFFICIENT_DATA`
  instead of `CANDIDATE`. That is the repair, not a regression.
- **Candidate directories.** Ordinary ids keep their directory names. An id containing `\` or
  `/`, or one that is itself `.`, `..` or empty, is re-homed. On POSIX an id containing `\` was a
  single component before, so after upgrading it is written once more under its new name.
- **Cost.** Canonical observation hashing adds a constant-factor cost to reading very large
  legacy histories; the reader remains linear in history length.
- **Python 3.9 and 3.12**, as before. Standard library only at runtime; `pytest` remains the
  single test-time dependency.

## 8. Tests and gates

Measured on the packaging head with Python 3.10.12: **18 suites, 1,708 assertions, 0 failures**.
CI runs the same suites on Python 3.9 and 3.12. The gates that matter for this release:

| suite | assertions | what it holds |
|---|---|---|
| `tests/test_evidence_integrity.py` | 346 | the frozen legacy evidence matrix (`docs/V142_COUNTEREXAMPLES.md`): quality law, epochs, trust boundary, retry and conflict |
| `tests/test_candidate_path.py` | 107 | the issue #15 matrix, run through the real CLI in a sandbox, plus 13 mutants applied to a throwaway copy of `tools/`, each required to turn its oracle red |
| `tests/test_mutation.py` | 77 | every repaired invariant has a mutant that must go red |
| `tests/test_release_shadow_only.py` | 10 | the shadow-only boundary: nothing is promoted, persisted or mutated |
| `tests/test_install_paths.py` | 14 | the pinned install routes name this version, and release notes exist for it |

`tests/test_oneliner_cleanup.sh` (the published OpenClaw one-liner cleans up on every outcome)
passes offline. The public-install and upgrade acceptances need a published tag and run after
it exists.

## 9. Canonical body identity

```text
CANONICAL_BODY_SHA256 = 7edec9f21e0bd50583e388e0bdc177f92ba8f0db6ce2bb61acd52b39d81e7767

artifact                FULL_FILE_SHA256   bytes         BODY_SHA256   bytes  desc
CLAUDE (canonical)      d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391
CODEX / AGENTSKILLS     d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391
HERMES                  9cce7a6c367b8b4a    4472    7edec9f21e0bd505    4385     49
OPENCLAW                d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391

CROSS_HOST_BODY_IDENTITY = PASS
```

Unchanged from 1.4.1. `python3 tools/adapters.py --hashes` recomputes it; `tests/test_adapters.py`
fails if any host's body drifts from the canonical one.

## 10. Install

| host | install |
|---|---|
| **Claude Code** | `claude plugin marketplace add ipeterpetrus/samewrite && claude plugin install samewrite@samewrite` |
| **Codex** | `codex plugin marketplace add ipeterpetrus/samewrite && codex plugin add samewrite@samewrite` |
| **Hermes Agent** | `hermes skills install https://raw.githubusercontent.com/ipeterpetrus/samewrite/v1.4.2/adapters/hermes/samewrite/SKILL.md --yes` |
| **OpenClaw** | `(d=$(mktemp -d) && trap 'rm -rf "$d"' EXIT && curl -fsSL https://github.com/ipeterpetrus/samewrite/archive/refs/tags/v1.4.2.tar.gz \| tar -xz -C "$d" && openclaw skills install "$d"/samewrite-*/skills/samewrite)` |

The raw-URL routes are pinned to the release tag, never to `main`:
`python3 tests/test_install_paths.py` checks offline that the pins name the version this
release actually is.

## Upgrading from 1.4.1

Nothing to migrate. Reinstall by the same route, or bump the plugin through its package
manager. A scheduler that reads the optimizer's `--json` should accept `output_schema_version` 2
and expect `PARTIAL_EVIDENCE` or `INSUFFICIENT_DATA` where evidence cannot support a promotion.
