# SameWrite 1.2.1 — release notes

A patch release with one fix. Nothing else changed: the skill, the guard and every claim from
1.2.0 are untouched, and **overall token-cost improvement is still `NOT_PROVEN`**.

## The fix

`bash hooks/install.sh` — the guard installation the README documents — failed on any machine where
`~/scripts` did not already exist, which is most machines.

```text
install -m 0755 "$PKG/write_noop_guard.py" "$DST"       # $DST defaults to $HOME/scripts/...
```

`install` does not create parent directories, and GNU's `-D` flag does not exist on macOS. The
result was an abort partway through, on the exact path a new user is told to take. The ledger line
immediately below it already did the `mkdir -p`; the guard line was missed.

Fixed with a portable `mkdir -p` before the copy.

## Why three releases shipped with it

Because no test had ever run the default destination. Every one of them set `SAMEWRITE_DST` to a
directory it had just created:

```text
tests/acceptance_upgrade.sh:  SAMEWRITE_DST="$W/bin/write_noop_guard.py"   (after mkdir -p "$W/bin")
tests/test_coexist.py:        SAMEWRITE_DST=self.dst                       (a TemporaryDirectory)
```

Each override was reasonable on its own — a test should not write into a real home. Together they
meant the default path, the one every user takes, was never exercised once. The bug is pre-existing:
it is in `v1.1.0` and `v1.2.0` too, and it is not a regression introduced by either.

**The general lesson, which is worth more than the fix:** an acceptance test that injects
environment overrides for convenience stops testing the default path, and the default path is the
product.

## What now prevents it

- `tests/test_coexist.py` runs `install.sh` with the **default** destination in a throwaway home and
  asserts the guard lands. The check was confirmed to go red against a copy of the tree with the
  `mkdir -p` removed, so it is a real oracle rather than a green light.
- `tests/acceptance_public.sh` installs from the **published marketplace** into an isolated `HOME`
  and `CLAUDE_CONFIG_DIR` and drives the whole user path: version, listing, on-demand body load, an
  ordinary coding prompt, guard install, idempotent reinstall, the opt-in output hook, and precise
  uninstall. This is the test that found the bug — local acceptance proves the code works, public
  acceptance proves that what was *published* works, and those are different claims.

## Unchanged from 1.2.0

| | |
|---|---|
| model-facing policy surface | byte-identical to `v1.1.0` — `skills/samewrite/SKILL.md`, `skills/edit-discipline/SKILL.md`, `hooks/write_noop_guard.py` |
| overall token-cost improvement | **NOT_PROVEN** (−1.7%, 8/10 fixtures, p = 0.109, smaller than the rig's own null-vs-null variance) |
| quality | non-inferior on correctness, safety, evidence completeness and authority compliance |
| Hermes Agent skill | VERIFIED (0.21.3, `1ad89ac`) — 80 B listing, 0 B unused body |
| Hermes observer | UNTESTED |
| GPT-5.6 Sol portability | UNTESTED (the attempt returned infrastructure errors, not a result) |
| `bash-output-shaping` | REJECTED · `listing-prune` DEFERRED |

## Upgrading

Nothing to do beyond the usual update. If you installed the guard on a machine where it silently
failed, re-run `bash hooks/install.sh`; it is idempotent and will now create the directory it needs.
