#!/usr/bin/env python3
"""samewrite_mode.py — namespaced on/off switch and optional one-line core injection.

    samewrite_mode.py prompt    UserPromptSubmit: reacts ONLY to samewrite's own phrases
    samewrite_mode.py session   SessionStart: injects the one-line core when SAMEWRITE_CORE=1

Owns exactly one state file, `<state dir>/samewrite-disabled`, where <state dir> is
SAMEWRITE_STATE_DIR, else CLAUDE_CONFIG_DIR, else ~/.claude. Never reads or writes
another plugin's flag, config, hook or status line. Never reacts to `normal mode`,
`stop ponytail`, `stop caveman` or `stop adhd mode` — those belong to other plugins,
and a shared off-switch would disarm all of them with one message.

Fail-open: any error → exit 0 with no output. A bug here must never block a prompt.
"""
import json, os, re, sys

VERSION = "1.1.0"          # pinned to .claude-plugin/plugin.json by tests/test_samewrite_mode.py
DISABLED = "samewrite-disabled"
CORE = ("samewrite: read to the semantic scope, ask only if the ambiguity is material, make "
        "the minimum correct change, and leave evidence that could have failed before exit. "
        "Controls: /samewrite on|off|status, `stop samewrite`.")
OFF = {"stop samewrite", "samewrite off", "samewrite stop", "disable samewrite"}
ON = {"samewrite on", "start samewrite", "enable samewrite"}
STATUS = {"samewrite status", "samewrite"}
SLASH = re.compile(r"^/samewrite(?::samewrite)?(?:\s+(\S+))?$")


def state_dir():
    return (os.environ.get("SAMEWRITE_STATE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
            or os.path.join(os.path.expanduser("~"), ".claude"))


def marker():
    return os.path.join(state_dir(), DISABLED)


def disabled():
    return os.path.lexists(marker())


def normalize(prompt):
    p = re.sub(r"\s+", " ", (prompt or "").strip().lower())
    return re.sub(r"[.!?\s]+$", "", p)


def parse(prompt):
    """-> 'on' | 'off' | 'status' | None. Whole-message match only: 'add a stop samewrite
    button' is a task, not a switch."""
    p = normalize(prompt)
    m = SLASH.match(p)
    if m:
        arg = m.group(1) or "status"
        return {"on": "on", "off": "off", "stop": "off", "status": "status"}.get(arg)
    if p in OFF:
        return "off"
    if p in ON:
        return "on"
    if p in STATUS:
        return "status"
    return None


def set_disabled(flag):
    m = marker()
    if flag:
        os.makedirs(os.path.dirname(m), exist_ok=True)
        fd = os.open(m, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.close(fd)
    elif os.path.lexists(m):
        os.unlink(m)


def emit(event, text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                             "additionalContext": text}}))


def on_prompt(data):
    action = parse(data.get("prompt"))
    if action is None:
        return
    if action == "off":
        set_disabled(True)
        emit("UserPromptSubmit", "SAMEWRITE OFF — samewrite's rules no longer apply, and its "
             "hooks stand down, until `samewrite on`. No other plugin was changed.")
    elif action == "on":
        set_disabled(False)
        emit("UserPromptSubmit", "SAMEWRITE ON — " + CORE)
    else:
        emit("UserPromptSubmit", "SAMEWRITE status: %s · core injection at session start: %s · "
             "state: %s" % ("off" if disabled() else "on",
                            "on" if os.environ.get("SAMEWRITE_CORE") == "1" else "off",
                            marker()))


def on_session():
    if disabled() or os.environ.get("SAMEWRITE_CORE") != "1":
        return
    print(CORE)


def main():
    try:
        if len(sys.argv) < 2 or sys.argv[1] not in ("prompt", "session"):
            return
        raw = sys.stdin.read(1024 * 1024)
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            return
        if sys.argv[1] == "prompt":
            on_prompt(data)
        else:
            on_session()
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
