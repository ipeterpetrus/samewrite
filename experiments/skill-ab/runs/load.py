"""Load run records, refusing anything the manifest marks analysis-ineligible.

The caveat that used to live in prose now lives here. `load("exploratory/ab6.jsonl")`
raises; `load(..., i_know=True)` returns the rows and prints what they are not.
"""
import json, pathlib

BASE = pathlib.Path(__file__).parent
MANIFEST = json.loads((BASE / "manifest.json").read_text())
BY_PATH = {e["path"]: e for e in MANIFEST["files"]}


def load(path, i_know=False):
    e = BY_PATH.get(str(path))
    if e is None:
        raise KeyError(f"{path} is not in manifest.json - unclassified data is not loadable")
    if not e["analysis_eligible"] and not i_know:
        raise ValueError(
            f"{path} is {e['evidence_class']}, not analysis-eligible. "
            f"n={e['n']} {e['unit']}, preregistered={e['preregistered']}. "
            "The conclusions rest on confirmatory_runs.jsonl. "
            "Pass i_know=True to load it anyway."
        )
    if not e["analysis_eligible"]:
        print(f"*** {e['evidence_class'].upper()} - NOT CONFIRMATORY: "
              f"{path} was not pre-registered. A number computed from it is a lead, not a result.")
    f = BASE / path if not str(path).startswith("..") else BASE / path
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


if __name__ == "__main__":
    ok = 0
    for p, e in BY_PATH.items():
        try:
            load(p); ok += 1
            assert e["analysis_eligible"], f"{p} loaded without a guard"
        except ValueError:
            assert not e["analysis_eligible"]
    assert ok == 1, f"exactly one file should load unguarded, got {ok}"
    print(f"OK: {len(BY_PATH)} files classified, {ok} analysis-eligible")
