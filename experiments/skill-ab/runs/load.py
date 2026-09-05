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
    # .splitlines() also splits on U+2028/U+2029, which are legal inside a JSON string:
    # one model answer containing them becomes two half-lines and the parse dies.
    return [json.loads(l) for l in (BASE / path).read_text().split("\n") if l.strip()]


if __name__ == "__main__":
    ok = 0
    for p, e in BY_PATH.items():
        try:
            load(p); ok += 1
            assert e["analysis_eligible"], f"{p} loaded without a guard"
        except ValueError:
            assert not e["analysis_eligible"]
    # Nailed down on purpose, not derived from the manifest: a self-test that reads its
    # own expectation out of the file it is testing will bless any future edit in silence.
    # Five, since ed366d8: the first Indonesian run, its English replication, two arms
    # of the first minimal-change replication, and the frozen third-party MBPP study.
    # The two minimal-change predictions failed; a pre-registered null is still
    # confirmatory evidence and still analysis-eligible.
    assert ok == 5, f"exactly five files should load unguarded, got {ok}"
    print(f"OK: {len(BY_PATH)} files classified, {ok} analysis-eligible")
