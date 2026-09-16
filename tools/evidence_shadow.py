#!/usr/bin/env python3
"""What each retained v1.4 finding WOULD see — computed, printed, and nothing else.

Phase 2 ports acquisition, not promotion. This reads a history file through the frozen kernel and
reports the four states a finding's dependency contract is judged against. It writes no candidate,
no artifact, no file, and it changes nothing: the whole point is to be able to answer "is the
evidence ready?" before any decision is wired to it.

    python3 tools/evidence_shadow.py ~/logs/carry_history.jsonl --scope default

Exit code is 0 whatever it finds. A shadow that failed the run would be a decision.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import evidence_history                                                 # noqa: E402
from evidence.absence import Absence                                    # noqa: E402
from evidence.certificate import evaluate_observation                   # noqa: E402
from evidence.container import history_integrity                        # noqa: E402
from evidence.decision import (make_sufficiency_facts, population_for, sufficiency,
                               world_state)                             # noqa: E402
from evidence.domains import AcquisitionIntegrity                       # noqa: E402
from evidence.promotion import promotable                               # noqa: E402
from evidence.registry import FINDING_FLOORS, dependency_contract       # noqa: E402
from evidence.values import make_epoch, make_finding_id, make_scope_id, make_workload_id


def shadow(path, scope_id="default", workload_class="", now=None):
    """-> (rows, facts). Pure: reads one file, allocates nothing on disk."""
    now = make_epoch(int(now or time.time()))
    container = evidence_history.read_container(path)
    scope, workload = make_scope_id(scope_id), make_workload_id(workload_class)
    population = population_for(container, scope, workload)
    state = history_integrity(container, Absence.KNOWN_ABSENT, scope, now)
    states = [evaluate_observation(m, now).effective for m in population.members]
    acquisition = AcquisitionIntegrity.worst(*states) if states else AcquisitionIntegrity.UNVERIFIED
    world = world_state(population.members, scope)
    # The sufficiency inputs come from the newest observation the history actually holds. Zeros
    # would report INSUFFICIENT for a reason that is about this reporter, not about the evidence.
    # The LEDGER inputs stay zero because phase 2 integrates no ledger acquisition, which is why
    # a ledger-only finding reads INSUFFICIENT here — that is the true state, not a placeholder.
    newest = population.members[-1] if population.members else None
    measure = (newest.payload.sessions if newest else 0,
               newest.payload.turns if newest else 0,
               newest.payload.carry_bytes if newest else 0,
               bool(newest and not newest.payload.shares.is_empty))
    rows = []
    for name in sorted(FINDING_FLOORS):
        contract = dependency_contract(name)
        enough = sufficiency(make_finding_id(name),
                             make_sufficiency_facts(measure[0], measure[1], measure[2],
                                                    measure[3], 0, 0, population.size, False))
        rows.append({
            "finding": name,
            "container_integrity": state.integrity.value,
            "acquisition_integrity": acquisition.value,
            "sufficiency": enough.value,
            "dependency_gate": promotable(contract, acquisition, state.integrity, enough, False,
                                          world, bool(population.members)),
        })
    return rows, {"records": len(container.records), "legacy": len(container.legacy),
                  "rejected": container.lines_rejected, "population": population.size,
                  "world": world.value, "reasons": [r.value for r in state.reasons]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("history")
    parser.add_argument("--scope", default="default")
    parser.add_argument("--workload", default="")
    args = parser.parse_args()
    rows, facts = shadow(args.history, args.scope, args.workload)
    print("container: %(records)d current, %(legacy)d legacy, %(rejected)d rejected lines"
          % facts)
    print("population: %(population)d observations, world %(world)s" % facts)
    if facts["reasons"]:
        print("container reasons: %s" % ", ".join(facts["reasons"]))
    print()
    print("%-26s %-10s %-12s %-12s %s" % ("finding", "container", "acquisition", "sufficiency",
                                          "EVIDENCE_READY_FOR_FINDING"))
    for row in rows:
        print("%-26s %-10s %-12s %-12s %s"
              % (row["finding"], row["container_integrity"], row["acquisition_integrity"],
                 row["sufficiency"], "YES" if row["dependency_gate"] else "NO"))
    print()
    print("shadow only: no candidate written, no artifact written, nothing promoted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
