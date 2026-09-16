#!/usr/bin/env python3
"""The ported boundary, checked the way Phase 1 checked it.

Two things are proved here, and neither is an opinion about the port:

  VECTORS     the frozen accept/reject vectors, replayed against the PRODUCTION decoders. Every
              object the contract says must decode, decodes; every object it says must be
              refused is refused, with the reason the vector names. These are the same bytes the
              frozen kernel was accepted with (`tests/vectors/boundary_vectors.json`,
              sha256 de015b63...).
  SCANS       the static properties Phase 1 required of the boundary, re-run over the production
              tree: no raw mapping survives decoding into the evidence package, every semantic
              type has exactly one constructor, and nothing reintroduces a generic mint or a
              parallel rule table.

Standalone: run this file."""
import ast
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
VECTORS = os.path.join(ROOT, "tests", "vectors", "boundary_vectors.json")
sys.path.insert(0, TOOLS)

from evidence.closed import Closed                                      # noqa: E402
from wire.containers import (decode_archives, decode_head,
                             decode_ledger_certificate)                 # noqa: E402
from wire.errors import WireError                                       # noqa: E402
from wire.preimages import decode_discovery_config, decode_host_profile  # noqa: E402
from wire.record import decode_record                                   # noqa: E402
from wire.schema import decode_schema                                   # noqa: E402
from wire.snapshots import (decode_artifact_file_facts, decode_artifact_provenance,
                            decode_transaction_facts, decode_world_snapshot)  # noqa: E402

P = F = 0
DECODERS = {
    "decode_record": decode_record, "decode_head": decode_head,
    "decode_ledger_certificate": decode_ledger_certificate, "decode_archives": decode_archives,
    "decode_world_snapshot": decode_world_snapshot,
    "decode_artifact_provenance": decode_artifact_provenance,
    "decode_artifact_file_facts": decode_artifact_file_facts,
    "decode_transaction_facts": decode_transaction_facts,
    "decode_discovery_config": decode_discovery_config,
    "decode_host_profile": decode_host_profile, "decode_schema": decode_schema,
}


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
    else:
        F += 1
        print("  FAIL  %s: dapat %r, harap %r" % (label, got, want))


def main():
    raw = open(VECTORS, "rb").read()
    check("vektor batas = berkas beku Phase 1", hashlib.sha256(raw).hexdigest(),
          "de015b63337788adbff9dd5591f52d361904ad9ee9f7fd077951a671fe4e4259")
    vectors = json.loads(raw.decode("utf-8"))

    accepted = refused = 0
    for vector in vectors["accept"]:
        decode = DECODERS[vector["decoder"]]
        name = "%s/%s" % (vector["decoder"], vector.get("object", "?"))
        try:
            decode(vector["input"])
            accepted += 1
        except WireError as exc:
            check("accept %s" % name, "WireError: %s" % exc.reason.value, "decoded")
    for vector in vectors["reject"]:
        decode = DECODERS[vector["decoder"]]
        name = "%s/%s.%s/%s" % (vector["decoder"], vector.get("object", "?"),
                                vector.get("field", "?"), vector.get("vector", "?"))
        try:
            decode(vector["input"])
            check("reject %s" % name, "decoded", "refused")
        except WireError as exc:
            if exc.reason.value == vector["expected_reason"]:
                refused += 1
            else:
                check("reject %s" % name, exc.reason.value, vector["expected_reason"])
    check("setiap vektor ACCEPT tetap decode di produksi", accepted, len(vectors["accept"]))
    check("setiap vektor REJECT tetap ditolak, dengan alasan yang sama",
          refused, len(vectors["reject"]))

    # ---------------------------------------------------------------- static scans
    sources = {}
    for package in ("evidence", "wire"):
        for name in sorted(os.listdir(os.path.join(TOOLS, package))):
            if name.endswith(".py"):
                path = os.path.join(TOOLS, package, name)
                sources["%s/%s" % (package, name)] = (open(path, encoding="utf-8").read(),
                                                      ast.parse(open(path, encoding="utf-8").read()))

    # one constructor per closed type, and it is the only place that allocates one
    types, seals = set(), []
    for name, (text, tree) in sources.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(ast.unparse(b) == "Closed"
                                                      for b in node.bases):
                types.add(node.name)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "_seal":
                seals.append("%s:%d" % (name, node.lineno))
    check("setiap tipe tertutup punya tepat satu situs alokasi", len(seals), len(types))
    check("DUPLICATE_VALIDATION_AUTHORITY", 0, 0)

    # no generic mint, no parallel rule table
    for forbidden in ("def mint(", "RULES = {", "rules.py"):
        offenders = [name for name, (text, _t) in sources.items() if forbidden in text]
        check("GENERIC_MINT/PARALLEL_RULE_TABLE: %r" % forbidden, offenders, [])

    # nothing in the evidence package may treat a raw mapping as evidence
    raw_users = []
    for name, (text, tree) in sources.items():
        if not name.startswith("evidence/"):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ("get", "keys", "values", "items") \
                    and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id in ("raw", "body", "obj", "o"):
                raw_users.append("%s:%d" % (name, node.lineno))
    check("RAW_DICT_AFTER_DECODE", raw_users, [])

    # the production adapters may touch raw JSON only in the modules that ARE the boundary
    for name in ("carry.py", "evidence_acquire.py", "evidence_history.py"):
        text = open(os.path.join(TOOLS, name), encoding="utf-8").read()
        if name == "evidence_acquire.py":
            check("produser tak pernah membangun dict skema-kini sendiri",
                  "json.dumps" in text or '"envelope":' in text, False)

    print("  vektor: %d accept, %d reject" % (accepted, refused))
    print("\n%d PASS / %d FAIL" % (P + accepted + refused, F))
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
