"""One error type for the decoding boundary, carrying the contract's own reason code."""
from evidence.domains import Reason


class WireError(ValueError):
    """Raw input that has no validated representation. It names WHERE and WHY."""

    def __init__(self, reason, path, detail=""):
        self.reason = reason
        self.path = path
        self.detail = detail
        super(WireError, self).__init__("%s at %s%s"
                                        % (reason.value, path or "<root>",
                                           (": " + detail) if detail else ""))


def fail(reason, path, detail=""):
    raise WireError(reason, path, detail)
