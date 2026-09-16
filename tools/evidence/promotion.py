"""Section 2 promotion gate - two independent axes, and nothing that converts one into the other.

The gate is where a finding's DECLARED dependency contract is enforced. Review A found the gap:
the registry stated `requires_container=INTACT` for every retained finding and nothing read it, so
a container that was DEGRADED -- the whole file, globally, which is the rule the scope reduction
established -- could still produce a CANDIDATE. A declaration nothing enforces is documentation,
and this phase exists to stop documenting rules instead of running them.

So the gate takes the finding's CONTRACT and the CONTAINER state. It takes the contract itself
rather than a finding id, because a gate that looks its own rules up in a global table can only
ever be tested against the rules that table happens to hold today -- and the mutation oracle said
so: with every current entry accepting the same acquisition states, a gate that ignored the
contract was indistinguishable from one that read it.
Nothing here is looser than before: the container requirement is a new refusal, and the world rule
is unchanged -- it is merely now declared by every entry rather than assumed by this function.
"""
from .domains import (AcquisitionIntegrity, AnalysisSufficiency, ContainerIntegrity, DomainError,
                      WorldState)
from .registry import DependencyContract

ACCEPTABLE_WITHOUT_FLAG = (AcquisitionIntegrity.INTACT,)
ACCEPTABLE_WITH_FLAG = (AcquisitionIntegrity.INTACT, AcquisitionIntegrity.BOUNDED)


def _boolean(name, flag):
    if flag is not True and flag is not False:
        # there is no truthiness here: the wire says boolean and the decoder produced one
        raise DomainError("%s must be a boolean, got %r" % (name, type(flag).__name__))
    return flag


def promotable(contract, integrity, container, sufficiency, accept_bounded, world_state,
               freshness_ok):
    """The whole gate. An unexpected loss can never be accepted as a chosen bound.

    `accept_bounded` is named for what it does: it accepts BOUNDED evidence, and nothing else.
    There is no `accept_partial` that could also cover DEGRADED.
    """
    if type(contract) is not DependencyContract:
        raise DomainError("contract is a DependencyContract, got %r" % type(contract).__name__)
    if not isinstance(integrity, AcquisitionIntegrity):
        raise DomainError("integrity is an AcquisitionIntegrity, got %r" % (integrity,))
    if not isinstance(container, ContainerIntegrity):
        raise DomainError("container is a ContainerIntegrity, got %r" % (container,))
    if not isinstance(sufficiency, AnalysisSufficiency):
        raise DomainError("sufficiency is an AnalysisSufficiency, got %r" % (sufficiency,))
    if not isinstance(world_state, WorldState):
        raise DomainError("world_state is a WorldState, got %r" % (world_state,))
    _boolean("accept_bounded", accept_bounded)
    _boolean("freshness_ok", freshness_ok)

    # --- the container this finding rests on, at the integrity the contract requires
    required = contract.container_integrity
    if container.rank > required.rank:
        return False

    # --- the acquisition, against the states the contract can rest on
    allowed = ACCEPTABLE_WITH_FLAG if accept_bounded else ACCEPTABLE_WITHOUT_FLAG
    allowed = tuple(state for state in allowed if state in contract.acquisition_integrity)
    if integrity not in allowed:
        return False

    # --- sufficiency, still an independent axis
    if sufficiency is not contract.sufficiency:
        return False

    # --- one world, which every entry declares because every finding is refused without it
    if contract.needs("world") and world_state is not WorldState.SINGLE_WORLD:
        return False
    return freshness_ok
