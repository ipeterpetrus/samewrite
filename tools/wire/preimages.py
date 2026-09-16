"""Decoders for the two digest preimages."""
from evidence.domains import Reason
from evidence.preimages import make_discovery_config, make_host_profile
from evidence.values import make_digest
from . import parse as P

CONFIG_FIELDS = ("config_schema", "root_digest", "include_patterns", "exclude_patterns",
                 "max_depth", "max_file_bytes", "follow_symlinks")
PROFILE_FIELDS = ("platform", "python_major_minor", "filesystem_type_of_target",
                  "path_separator", "case_sensitivity_of_target")


def decode_discovery_config(raw, path="discovery_config"):
    body = P.members(raw, path, CONFIG_FIELDS)
    patterns = {}
    for name in ("include_patterns", "exclude_patterns"):
        patterns[name] = tuple(P.array(body[name], path + "." + name))
    return P.built(path, make_discovery_config, body["config_schema"],
                   P.built(path, make_digest, body["root_digest"], "root_digest"),
                   patterns["include_patterns"], patterns["exclude_patterns"],
                   body["max_depth"], body["max_file_bytes"], body["follow_symlinks"])


def decode_host_profile(raw, path="host_profile"):
    body = P.members(raw, path, PROFILE_FIELDS)
    return P.built(path, make_host_profile, *[body[f] for f in PROFILE_FIELDS])
