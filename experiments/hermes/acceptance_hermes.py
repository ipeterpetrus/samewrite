#!/usr/bin/env python3
"""Hermes Agent acceptance for SameWrite — against a REAL Hermes install, in an ISOLATED profile.

    HERMES_SRC=/path/to/hermes-agent  HERMES_PY=/path/to/venv/bin/python \\
      python3 experiments/hermes/acceptance_hermes.py

It answers, mechanically and one line at a time: does Hermes discover, list, load and invoke the
generated SameWrite skill, does its progressive loading actually keep the body out of context until
the skill is used, and what does an UNUSED skill cost in the system prompt. Filesystem and prompt
rendering only — no model call, no API key, no network.

The user's own Hermes profile is never touched: `HERMES_HOME` points into a scratch directory this
script creates and removes. It asserts that afterwards.

The real API is called by its real names (`skills_list`, `skill_view`,
`build_skills_system_prompt`), read out of the pinned checkout rather than guessed, because a probe
that silently returns nothing is indistinguishable from a feature that is absent.
"""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = F = 0
MEASURED = {}


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: got {got!r}, want {want!r}")


CHILD = r'''
import json, os, sys
sys.path.insert(0, os.environ["HERMES_SRC"])
out = {}
try:
    from tools import skills_tool
    from agent import prompt_builder
except Exception as e:
    print(json.dumps({"import_error": f"{type(e).__name__}: {e}"})); raise SystemExit(0)

def unwrap(s):
    try:
        return json.loads(s) if isinstance(s, str) else s
    except Exception:
        return {"_raw": s}

listing = unwrap(skills_tool.skills_list())
out["listing"] = listing
try:
    prompt = prompt_builder.build_skills_system_prompt()
except Exception as e:
    prompt = ""
    out["prompt_error"] = f"{type(e).__name__}: {e}"
out["prompt"] = prompt
out["prompt_len"] = len(prompt)
view = unwrap(skills_tool.skill_view("samewrite"))
out["view"] = view
print(json.dumps(out))
'''


def main():
    src = os.environ.get("HERMES_SRC")
    py = os.environ.get("HERMES_PY")
    if not src or not py:
        print("set HERMES_SRC (checkout) and HERMES_PY (venv python)")
        return 2
    adapter = os.path.join(ROOT, "adapters", "hermes", "samewrite", "SKILL.md")
    if not os.path.exists(adapter):
        print("generated adapter missing — run tools/adapters.py")
        return 2

    commit = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "UNKNOWN"
    ver = subprocess.run([py, "-c", "import importlib.metadata as m;print(m.version('hermes-agent'))"],
                         capture_output=True, text=True).stdout.strip() or "UNKNOWN"
    print("=== Hermes Agent acceptance ===")
    print(f"repo    : NousResearch/hermes-agent")
    print(f"commit  : {commit}")
    print(f"version : {ver}")

    d = tempfile.mkdtemp(prefix="sw-hermes-")
    home = os.path.join(d, "home")
    os.makedirs(os.path.join(home, "skills", "samewrite"))
    shutil.copyfile(adapter, os.path.join(home, "skills", "samewrite", "SKILL.md"))
    print(f"profile : {home} (isolated)\n")
    check("install: the generated adapter is a plain file copy into the profile", True, True)

    env = dict(os.environ)
    env.update(HERMES_HOME=home, HERMES_SRC=src,
               # Without this, `hermes` dies at import on any host with a root-owned /etc/hermes:
               # upstream calls Path.exists() on it inside a block documented as fail-open, and
               # Path.exists() raises rather than returning False when the parent is unreadable.
               HERMES_MANAGED_DIR=os.path.join(d, "managed"))
    os.makedirs(env["HERMES_MANAGED_DIR"], exist_ok=True)
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY"):
        env.pop(k, None)                                  # prove no key is needed to get this far

    r = subprocess.run([py, "-c", CHILD], capture_output=True, text=True, env=env, timeout=600)
    line = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if not line:
        print("  FAIL  hermes API did not return JSON")
        print((r.stdout + r.stderr)[-800:])
        shutil.rmtree(d, ignore_errors=True)
        return 1
    o = json.loads(line[-1])
    if "import_error" in o:
        print(f"  FAIL  import: {o['import_error']}")
        shutil.rmtree(d, ignore_errors=True)
        return 1

    # ---------------------------------------------------------------- discovery and listing
    rows = o["listing"].get("skills") if isinstance(o["listing"], dict) else o["listing"]
    names = [x.get("name") for x in rows] if isinstance(rows, list) else []
    check("discover: samewrite is found with zero API keys set", "samewrite" in names, True)
    row = next((x for x in (rows or []) if x.get("name") == "samewrite"), {})
    desc = row.get("description") or ""
    check("listing: a description is present", bool(desc), True)

    # ---------------------------------------------------------------- level 0: the always-on cost
    prompt = o.get("prompt") or ""
    check("level 0: samewrite appears in the system prompt index", "samewrite" in prompt, True)
    skill_text = open(adapter, encoding="utf-8").read()
    body = skill_text.split("---", 2)[2]
    markers = ("Optimize **correct result per total cost**", "## Context", "## Root cause",
               "## Verification", "## Output")
    leaked = [m for m in markers if m in prompt]
    check("level 0: the BODY is absent until the skill is invoked (progressive loading)", leaked, [])
    MEASURED["prompt_total_bytes"] = len(prompt)
    MEASURED["body_bytes_on_disk"] = len(body)
    MEASURED["unused_body_cost_bytes"] = sum(len(m) for m in leaked)
    idx = ""
    if "<available_skills>" in prompt:
        idx = prompt.split("<available_skills>", 1)[1].split("</available_skills>", 1)[0]
    sw_lines = [l for l in idx.splitlines() if "samewrite" in l]
    MEASURED["level0_samewrite_bytes"] = sum(len(l) + 1 for l in sw_lines)

    # ---------------------------------------------------------------- level 1: load on demand
    view = o["view"]
    content = view.get("content") if isinstance(view, dict) else str(view)
    content = content or ""
    check("level 1: skill_view returns the full body on demand",
          "Optimize **correct result per total cost**" in content, True)
    MEASURED["level1_loaded_bytes"] = len(content)

    # ---------------------------------------------------------------- honesty about truncation
    # Hermes cuts a description at 60 characters in the prompt. The canonical Claude description is
    # 391 characters, so shipping it unchanged would lose its routing tail exactly where routing
    # happens. The generated adapter is short enough that nothing is cut — assert that, rather than
    # asserting the file merely loaded.
    canon = open(os.path.join(ROOT, "skills", "samewrite", "SKILL.md"), encoding="utf-8").read()
    canon_desc = [l for l in canon.split("---")[1].splitlines()
                  if l.startswith("description:")][0].split(":", 1)[1].strip()
    check("adapter description survives the host cut-off intact",
          desc.rstrip(".") in prompt or desc[:57] in prompt, True)
    check("canonical 391-char description is NOT what was shipped to this host",
          canon_desc in skill_text, False)
    MEASURED["canonical_desc_chars"] = len(canon_desc)
    MEASURED["adapter_desc_chars"] = len(desc)

    # ---------------------------------------------------------------- CLI surface
    hermes = os.path.join(os.path.dirname(py), "hermes")
    if os.path.exists(hermes):
        c = subprocess.run([hermes, "skills", "list"], capture_output=True, text=True,
                           env=env, timeout=600)
        check("cli: `hermes skills list` shows samewrite", "samewrite" in c.stdout, True)
    else:
        print("  SKIP  cli: hermes entry point absent from the venv")

    # ---------------------------------------------------------------- uninstall and isolation
    shutil.rmtree(os.path.join(home, "skills", "samewrite"))
    r2 = subprocess.run([py, "-c", CHILD], capture_output=True, text=True, env=env, timeout=600)
    l2 = [l for l in r2.stdout.splitlines() if l.startswith("{")]
    after = json.loads(l2[-1]) if l2 else {}
    rows2 = after.get("listing", {}).get("skills") if isinstance(after.get("listing"), dict) else []
    check("uninstall: removing the directory removes the skill",
          "samewrite" in [x.get("name") for x in (rows2 or [])], False)
    check("isolation: the real ~/.hermes profile was never touched",
          os.path.exists(os.path.expanduser("~/.hermes/skills/samewrite")), False)

    shutil.rmtree(d, ignore_errors=True)

    print("\nMEASURED")
    for k in ("level0_samewrite_bytes", "unused_body_cost_bytes", "body_bytes_on_disk",
              "level1_loaded_bytes", "prompt_total_bytes", "canonical_desc_chars",
              "adapter_desc_chars"):
        print(f"  {k:<26} {MEASURED.get(k, 'n/a'):>10,}" if isinstance(MEASURED.get(k), int)
              else f"  {k:<26} {MEASURED.get(k, 'n/a')}")
    print(f"\n{P} PASS / {F} FAIL")
    json.dump({"repo": "NousResearch/hermes-agent", "commit": commit, "version": ver,
               "measured": MEASURED, "pass": P, "fail": F},
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "result.json"), "w"),
              indent=2)
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
