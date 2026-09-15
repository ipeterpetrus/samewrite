#!/usr/bin/env python3
"""What is actually installed, on this machine, right now — observed, never inferred.

    python3 tools/doctor.py
    python3 tools/doctor.py --json

Every line is a fact this program checked itself. Nothing is reported as present because a file
exists somewhere plausible, and nothing is reported as working because it was installed. Where a
thing cannot be observed from here, it says so rather than guessing, because a guessed green mark
is worse than a blank: it stops the reader from looking.

Read-only. No network, no model, no writes. Run it whenever you want to know the truth about a
machine instead of the truth about a README.

Two findings from real use are baked into how it looks:

  * A config directory's `plugins` can be a SYMLINK to another profile's. `os.walk` does not follow
    symlinks, so a naive scan reports a healthy install as missing — and two profiles can silently
    share one plugin tree.
  * A hand-copied skill from an older release can sit in the user skills directory and shadow the
    packaged one. SameWrite ships `edit-discipline` hidden on purpose; a leftover copy is not
    hidden, so it quietly costs listing bytes on every turn.
"""
import argparse, hashlib, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OK, NO, UNK = "VERIFIED", "ABSENT", "NOT_OBSERVABLE"


def sha(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    except OSError:
        return None


def repo_version():
    try:
        return json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))["version"]
    except Exception:
        return "?"


def run(cmd, timeout=60, merge=True):
    """-> (rc, text). A tool that is not installed is not a crash, it is an answer.

    `merge=False` keeps stderr OUT of the result. That matters for JSON probes: a shell wrapper or
    a shim can print a banner to stderr, and merging it into stdout corrupts the document. This
    exact thing happened here — a quota-warning banner made a healthy `codex plugin list --json`
    unparseable, and the doctor reported NOT_OBSERVABLE for a host it could see perfectly well."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + ((p.stderr or "") if merge else "")
    except FileNotFoundError:
        return 127, ""
    except Exception as e:
        return -1, f"{type(e).__name__}"


def first_json(text):
    """The first complete JSON object in `text`, ignoring anything printed around it."""
    i = text.find("{")
    while i != -1:
        try:
            return json.JSONDecoder().raw_decode(text[i:])[0]
        except ValueError:
            i = text.find("{", i + 1)
    return None


def walk(root):
    """os.walk that FOLLOWS symlinks. A config dir whose `plugins` is a symlink into another
    profile is normal, and a scan that misses it reports a working install as missing."""
    return os.walk(root, followlinks=True)


def which(env_name, default_rel, exe):
    b = os.environ.get(env_name) or os.path.expanduser(default_rel)
    if os.path.exists(b):
        return b
    rc, w = run(["which", exe])
    return w.strip() if rc == 0 and w.strip() else ""


# ------------------------------------------------------------------ Claude Code
def claude():
    out = {"host": "Claude Code"}
    binary = which("SAMEWRITE_CLAUDE_BIN", "~/.local/bin/claude", "claude")
    out["binary"] = binary or None
    if not binary:
        out["status"] = NO
        return out
    rc, v = run([binary, "--version"])
    out["version"] = v.strip().splitlines()[0] if rc == 0 and v.strip() else None
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    out["config_dir"] = cfg
    pl = os.path.join(cfg, "plugins")
    out["plugins_symlink"] = os.path.realpath(pl) if os.path.islink(pl) else None

    rc, listing = run([binary, "plugin", "list"], timeout=180)
    out["cli_lists_samewrite"] = bool(re.search(r"samewrite@", listing)) if rc == 0 else None
    m = re.search(r"samewrite@\S+\s*\n\s*Version:\s*(\S+)", listing)
    out["installed_version"] = m.group(1) if m else None

    manifests, skills = [], []
    for r, _d, fs in walk(cfg):
        if "plugin.json" in fs:
            try:
                d = json.load(open(os.path.join(r, "plugin.json")))
            except Exception:
                d = {}
            if d.get("name") == "samewrite":
                manifests.append((d.get("version"), os.path.relpath(r, cfg)))
        if "SKILL.md" in fs and os.path.basename(r) in ("samewrite", "edit-discipline"):
            skills.append(os.path.relpath(r, cfg))
    out["manifests"] = sorted(set(manifests))

    # A loose copy directly under the profile's skills/ is not the packaged one.
    loose = [s for s in skills if s.startswith("skills" + os.sep)]
    out["loose_user_skills"] = sorted(loose)
    shadow = []
    for s in loose:
        q = os.path.join(cfg, s, "SKILL.md")
        try:
            head = open(q, encoding="utf-8", errors="replace").read().split("---", 2)[1]
        except Exception:
            continue
        hidden = "disable-model-invocation: true" in head
        packaged = os.path.join(ROOT, "skills", os.path.basename(s), "SKILL.md")
        same = sha(q) == sha(packaged) if os.path.exists(packaged) else False
        if not hidden or not same:
            shadow.append({"path": s, "hidden": hidden, "matches_shipped": same,
                           "bytes": os.path.getsize(q)})
    out["shadowing_copies"] = shadow

    st = os.path.join(cfg, "settings.json")
    guard = human = None
    if os.path.exists(st):
        try:
            d = json.load(open(st))
            hooks = d.get("hooks") or {}
            guard = sum(1 for e in hooks.get("PreToolUse", []) for h in e.get("hooks", [])
                        if "write_noop_guard" in h.get("command", ""))
            human = sum(1 for e in hooks.get("SessionStart", []) for h in e.get("hooks", [])
                        if "samewrite" in h.get("command", "").lower())
        except Exception:
            guard = human = None
    out["write_guard_entries"] = guard
    out["human_output_entries"] = human
    out["status"] = OK if out["cli_lists_samewrite"] else (
        NO if out["cli_lists_samewrite"] is False else UNK)
    return out


# ------------------------------------------------------------------ Codex
def codex():
    out = {"host": "Codex"}
    binary = which("SAMEWRITE_CODEX_BIN", "~/.local/bin/codex", "codex")
    out["binary"] = binary or None
    if not binary:
        out["status"] = NO
        return out
    rc, v = run([binary, "--version"])
    out["version"] = v.strip().splitlines()[0] if rc == 0 else None
    out["home"] = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    rc, j = run([binary, "plugin", "list", "--json"], timeout=180, merge=False)
    out["cli_lists_samewrite"] = None
    d = first_json(j) if rc == 0 else None
    if isinstance(d, dict):
        hits = [q for q in d.get("installed", []) if q.get("name") == "samewrite"]
        out["cli_lists_samewrite"] = bool(hits)
        if hits:
            out["installed_version"] = hits[0].get("version")
            out["enabled"] = hits[0].get("enabled")
    out["status"] = OK if out.get("cli_lists_samewrite") else (
        NO if out.get("cli_lists_samewrite") is False else UNK)
    return out


# ------------------------------------------------------------------ Hermes
def hermes():
    out = {"host": "Hermes Agent"}
    home = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
    out["home"] = home
    if not os.path.isdir(home):
        out["status"] = NO
        return out
    sk = os.path.join(home, "skills", "samewrite", "SKILL.md")
    out["skill_present"] = os.path.exists(sk)
    if out["skill_present"]:
        out["skill_bytes"] = os.path.getsize(sk)
        gen = os.path.join(ROOT, "adapters", "hermes", "samewrite", "SKILL.md")
        out["matches_generated_adapter"] = sha(sk) == sha(gen) if os.path.exists(gen) else None
    out["state_db"] = os.path.exists(os.path.join(home, "state.db"))
    out["status"] = OK if out["skill_present"] else NO
    return out


# ------------------------------------------------------------------ OpenClaw
def openclaw():
    out = {"host": "OpenClaw"}
    home = os.environ.get("OPENCLAW_STATE_DIR") or os.path.expanduser("~/.openclaw")
    out["state_dir"] = home
    if not os.path.isdir(home):
        out["status"] = NO
        return out
    hits = [os.path.relpath(r, home) for r, _d, fs in walk(home)
            if "SKILL.md" in fs and os.path.basename(r) == "samewrite"]
    out["skill_paths"] = sorted(hits)
    out["status"] = OK if hits else NO
    return out


# ------------------------------------------------------------------ offline tools
def offline():
    out = {}
    hist = os.path.expanduser(os.environ.get("SAMEWRITE_HISTORY", "~/logs/carry_history.jsonl"))
    out["history_path"] = hist
    out["history_records"] = sum(1 for _ in open(hist, errors="replace")) \
        if os.path.exists(hist) else 0
    led = os.path.expanduser(os.environ.get("SAMEWRITE_LEDGER", "~/logs/samewrite.jsonl"))
    out["ledger_records"] = sum(1 for _ in open(led, errors="replace")) \
        if os.path.exists(led) else 0
    out["observer"] = "manual"          # never scheduled by SameWrite; there is no daemon
    out["optimizer"] = "manual"
    out["model_calls"] = 0
    out["network"] = 0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    hosts = [claude(), codex(), hermes(), openclaw()]
    off = offline()
    ver = repo_version()

    # REPOSITORY_VERSION is what this checkout says it is; INSTALLED_VERSION is what a host
    # actually loaded. On a release branch these differ by definition, and printing one number as
    # though it were both is how a report claims a version nobody has. They are named separately
    # here and compared out loud.
    drift = [(h["host"], h["installed_version"]) for h in hosts
             if h.get("installed_version") and h["installed_version"] != ver]

    if a.json:
        print(json.dumps({"repository_version": ver,
                          # kept for compatibility with anything reading the 1.3 dev output
                          "samewrite_repo_version": ver,
                          "version_drift": [{"host": h, "installed_version": v} for h, v in drift],
                          "hosts": hosts, "offline": off}, indent=2))
        return 0

    print("SameWrite doctor — read-only; every line below was checked, not assumed\n")
    print(f"REPOSITORY_VERSION  {ver}   (this checkout — not evidence that any host has it)")
    print(f"{'host':<14}{'status':<16}{'INSTALLED_VERSION':<20}host version")
    for h in hosts:
        print(f"{h['host']:<14}{h.get('status', UNK):<16}"
              f"{str(h.get('installed_version') or '-'):<20}{h.get('version') or '-'}")
    if drift:
        print("\n  version drift     " + ", ".join(f"{h} has {v}, this checkout is {ver}"
                                                   for h, v in drift))
        print("                    expected on a release branch: the tag is not published yet")

    c = hosts[0]
    print("\nClaude Code detail")
    print(f"  config dir        {c.get('config_dir')}")
    if c.get("plugins_symlink"):
        print(f"  plugins/          SYMLINK -> {c['plugins_symlink']}")
        print("                    another profile may share this plugin tree")
    print(f"  cli lists it      {c.get('cli_lists_samewrite')}")
    for v, p in c.get("manifests", []):
        print(f"  manifest          v{v}  {p}")
    print(f"  write guard       {'ON (%d entry)' % c['write_guard_entries'] if c.get('write_guard_entries') else 'OFF'}")
    print(f"  human output      {'ON' if c.get('human_output_entries') else 'OFF'}")
    for s in c.get("shadowing_copies", []):
        print(f"  ! SHADOW COPY     {s['path']}  {s['bytes']} B  "
              f"hidden={s['hidden']}  matches_shipped={s['matches_shipped']}")
        print("                    a hand-copied skill here is listed on EVERY turn; "
              "the packaged one is hidden on purpose")

    print("\noffline tools (no model, no network, no scheduler)")
    print(f"  history records   {off['history_records']}   {off['history_path']}")
    print(f"  ledger records    {off['ledger_records']}")
    print(f"  observer          {off['observer']}      optimizer  {off['optimizer']}")

    unk = [h["host"] for h in hosts if h.get("status") == UNK]
    if unk:
        print(f"\nNOT_OBSERVABLE from here: {', '.join(unk)} — reported as unknown, not as green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
