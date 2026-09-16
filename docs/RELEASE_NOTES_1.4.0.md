# SameWrite 1.4.0 — release notes

**One sentence.** The optimizer's evidence is now typed, integrity-checked and read-only: 1.4
measures and evaluates evidence in shadow mode, and automatic candidate promotion and persistence
are deliberately not part of this release.

**The feature people would expect from this cycle is not here, on purpose.** Evidence-gated
promotion — a finding that clears its dependency contract writing a candidate proposal by itself —
was built and refused by its own review. What ships is the half that can be trusted today: the
measurement, the integrity semantics, and a shadow evaluation that prints what a decision *would*
see and writes nothing.

## What changed

- **A typed evidence kernel.** 35 files under `tools/evidence/` and `tools/wire/`, ported byte for
  byte from the frozen Phase-1 contract; their concatenated sha256 is
  `88e4b48486eaa2a72abcdc4e52542113834e3c96bf08777fd67d13ac1adb82fd`, and every test run re-checks
  it. Nothing in this release modifies a kernel file.
- **Acquisition produces evidence, not totals.** A sweep emits a certificate of what it actually
  read: the sources it selected, the identity each had when it was selected, and one outcome per
  source. A sweep that read nothing writes a **tombstone**, not a measurement with no shares.
- **History schema 4.** The current write format chains each record to the one before it by
  position and digest. The read-tail-then-append sequence is serialised with an advisory lock, and
  a lock that cannot be taken stops the append rather than proceeding without one.
- **Legacy generations are read fail-closed.** Schemas 0, 1, 2 and 3 are read far enough to be
  counted and attributed. Facts their schema never carried stay `ABSENT`, and a container that
  holds one is `UNVERIFIED`: previous-generation evidence cannot acquire current trust by
  defaulting. A current-generation record that does not decode is damage — never silently demoted
  to a legacy record.
- **Container integrity is global.** One container, one integrity answer, independent of which
  records a particular finding looks at. An unparseable line, a duplicate position, a broken chain
  or a stale head changes the container's state rather than being reported as a footnote.
- **Two axes, kept apart.** Acquisition integrity — `INTACT`, `BOUNDED` (a bound someone chose),
  `DEGRADED` (a loss nobody chose), `FAILED`, `UNVERIFIED` — is separate from analysis
  sufficiency. "The evidence is intact" and "there is enough of it" are different questions, and
  blurring them is how an optimizer talks itself into acting on a partial read.
- **Privacy-safe provenance.** Sizes, shares and digests. No paths, no prompts, no tool content; a
  planted canary is proved absent from every output.
- **Shadow evaluation.**

  ```bash
  python3 tools/evidence_shadow.py ~/logs/carry_history.jsonl --scope default
  ```

  One row per retained finding — container state, acquisition integrity, sufficiency, whether it
  would promote and why not — then exit 0 whatever it found. It writes no candidate, no artifact
  and no file.

## Retained findings, evaluated in shadow

```text
listing_cost
write_guard_retirement
```

## Intentionally not active in 1.4.0

```text
automatic promotion
automatic candidate persistence
automatic policy mutation
windowing
host shift
carry_share_concentration
carry_bytes_trend
```

Automatic evidence-based candidate persistence remains disabled while the transaction and API
boundary around it is still being researched. `NO_ACTION` and "the evidence is not sufficient" are
first-class answers here; nothing in this release promotes itself, and nothing writes a proposal
without a human running a command that says so.

## Install

```text
Claude Code   claude plugin marketplace add ipeterpetrus/samewrite && claude plugin install samewrite@samewrite
Codex         codex  plugin marketplace add ipeterpetrus/samewrite && codex  plugin add     samewrite@samewrite
Hermes Agent  hermes skills install https://raw.githubusercontent.com/ipeterpetrus/samewrite/v1.4.0/adapters/hermes/samewrite/SKILL.md --yes
OpenClaw      (d=$(mktemp -d) && trap 'rm -rf "$d"' EXIT \
               && curl -fsSL https://github.com/ipeterpetrus/samewrite/archive/refs/tags/v1.4.0.tar.gz | tar -xz -C "$d" \
               && openclaw skills install "$d"/samewrite-*/skills/samewrite)
```

The raw-URL routes are pinned to this release, as in every cycle: a reader must not end up
installing a version other than the one whose notes they are reading
(`python3 tests/test_install_paths.py` checks that pairing offline).

## Policy body, identical everywhere — and unchanged by this release

The skill body did not change in 1.4.0. The version moved; the policy did not.

```text
artifact                FULL_FILE_SHA256   bytes         BODY_SHA256   bytes  desc
CLAUDE (canonical)      d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391
CODEX / AGENTSKILLS     d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391
HERMES                  9cce7a6c367b8b4a    4472    7edec9f21e0bd505    4385    49
OPENCLAW                d7c65ee5a4496263    4816    7edec9f21e0bd505    4385   391

CROSS_HOST_BODY_IDENTITY = PASS
```

## Evidence claims, unchanged

```text
TOTAL_SAVINGS=NOT_PROVEN
WORLD_BEST_CLAIM=NOT_TESTED
```

The best end-to-end measurement remains −1.7%, cheaper on 8 of 10 fixtures at p = 0.109 — smaller
than the same rig's variance between two byte-identical arms. Typed evidence does not change that
number; it changes how honestly the optimizer can describe the evidence behind it.

## Compatibility

- Existing history files keep working: 0/1/2/3 are read, and a 1.3 history stays readable and
  reportable after upgrading.
- `python3 tools/optimize.py` behaves as it did in 1.3 for a previous-generation history,
  including its opt-in `--emit-candidate` proposal writer, which is unchanged 1.3 behaviour and
  runs only when a human passes that flag.
- Hooks, the guard, the skill body and the adapters are untouched by this release.
