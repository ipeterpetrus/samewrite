"""The two digest preimages: function inputs, not wire members, each with one constructor."""
import dataclasses
import typing

from . import forms as f
from .canon import CanonMap, CanonSeq
from .closed import Closed, ConstructionError
from .domains import Reason
from .values import Digest

DISCOVERY_CONFIG_SCHEMA = 1


def _require(ok, field, detail):
    if not ok:
        raise ConstructionError(Reason.CERT_BAD_TYPE, field, detail)


@dataclasses.dataclass(frozen=True, init=False)
class DiscoveryConfig(Closed):
    config_schema: int
    root_digest: Digest
    include_patterns: typing.Tuple[str, ...]
    exclude_patterns: typing.Tuple[str, ...]
    max_depth: int
    max_file_bytes: int
    follow_symlinks: bool

    def canon(self):
        return CanonMap([("config_schema", self.config_schema),
                         ("root_digest", self.root_digest.hex),
                         ("include_patterns", CanonSeq(self.include_patterns)),
                         ("exclude_patterns", CanonSeq(self.exclude_patterns)),
                         ("max_depth", self.max_depth),
                         ("max_file_bytes", self.max_file_bytes),
                         ("follow_symlinks", self.follow_symlinks)])

    @property
    def policy_ok(self):
        """Identity ACCEPTS follow_symlinks; the 1.4 sweep POLICY still refuses to run that way."""
        return self.follow_symlinks is False


@dataclasses.dataclass(frozen=True, init=False)
class HostProfile(Closed):
    platform: str
    python_major_minor: str
    filesystem_type_of_target: str
    path_separator: str
    case_sensitivity_of_target: str

    def canon(self):
        return CanonMap([("platform", self.platform),
                         ("python_major_minor", self.python_major_minor),
                         ("filesystem_type_of_target", self.filesystem_type_of_target),
                         ("path_separator", self.path_separator),
                         ("case_sensitivity_of_target", self.case_sensitivity_of_target)])


def make_discovery_config(config_schema, root_digest, include_patterns, exclude_patterns,
                          max_depth, max_file_bytes, follow_symlinks, field="discovery_config"):
    """The supported schema is decided HERE. In phase 1R the decoder required schema 1 and the
    parallel rule table accepted any int, so an internal caller could build a config no decoder
    would produce (Review B, B2)."""
    _require(f.is_int(config_schema) and config_schema == DISCOVERY_CONFIG_SCHEMA,
             field + ".config_schema", "this reader supports config schema %d"
             % DISCOVERY_CONFIG_SCHEMA)
    _require(type(root_digest) is Digest, field + ".root_digest", "a validated Digest")
    for name, patterns in (("include_patterns", include_patterns),
                           ("exclude_patterns", exclude_patterns)):
        _require(type(patterns) is tuple, field + "." + name, "a tuple of strings")
        for pattern in patterns:
            _require(f.is_str(pattern), field + "." + name, "a tuple of strings")
    _require(f.is_int(max_depth) and max_depth >= -1, field + ".max_depth", "an int >= -1")
    _require(f.is_nat(max_file_bytes), field + ".max_file_bytes", "a non-negative int")
    _require(f.is_bool(follow_symlinks), field + ".follow_symlinks", "exactly true or false")
    return DiscoveryConfig._seal(config_schema=config_schema, root_digest=root_digest,
                                 include_patterns=include_patterns,
                                 exclude_patterns=exclude_patterns, max_depth=max_depth,
                                 max_file_bytes=max_file_bytes, follow_symlinks=follow_symlinks)


def make_host_profile(platform, python_major_minor, filesystem_type_of_target, path_separator,
                      case_sensitivity_of_target, field="host_profile"):
    values = {"platform": platform, "python_major_minor": python_major_minor,
              "filesystem_type_of_target": filesystem_type_of_target,
              "path_separator": path_separator,
              "case_sensitivity_of_target": case_sensitivity_of_target}
    for name, value in values.items():
        _require(f.is_str(value), field + "." + name, "a string")
    return HostProfile._seal(**values)
