#!/usr/bin/env bash
# PUBLIC INSTALL ACCEPTANCE — installs SameWrite the way a stranger would, from the published
# GitHub marketplace, into a HOME and CLAUDE_CONFIG_DIR that exist only for this run.
#
#   bash tests/acceptance_public.sh              # expects the version in .claude-plugin/plugin.json
#   SW_EXPECT_VERSION=1.2.0 bash tests/acceptance_public.sh
#
# NOT part of CI: it needs network, a logged-in Claude Code CLI, and it spends a few small model
# calls. Run after publishing a release.
#
# The point is that nothing local is trusted. tests/acceptance_upgrade.sh installs from a worktree,
# which proves the code works; this proves that what was actually PUBLISHED works, which is a
# different claim and the only one a user can act on. The developer's real profile is never touched:
# HOME and CLAUDE_CONFIG_DIR both point inside a temporary directory, and only the credentials file
# is copied in (cp, never read) so the CLI can authenticate. It is deleted at the end.
set -u
REPO_SLUG="${SW_REPO:-ipeterpetrus/samewrite}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY=/usr/bin/python3
WANT="${SW_EXPECT_VERSION:-$("$PY" -c "import json;print(json.load(open('$REPO/.claude-plugin/plugin.json'))['version'])")}"
CLAUDE="${SAMEWRITE_CLAUDE_BIN:-$HOME/.local/bin/claude}"
CRED="${SAMEWRITE_CRED:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json}"

W=$(mktemp -d /tmp/sw-public-XXXXXX)
CFG="$W/cfg"; mkdir -p "$CFG" "$W/home" "$W/work"
cp "$CRED" "$CFG/.credentials.json" && chmod 600 "$CFG/.credentials.json"
echo '{}' > "$CFG/settings.json"
P=0; F=0
ok()  { P=$((P+1)); printf '  PASS  %s\n' "$1"; }
bad() { F=$((F+1)); printf '  FAIL  %s\n' "$1"; }
chk() { if [ "$2" = "$3" ]; then ok "$1 ($2)"; else bad "$1: got '$2', want '$3'"; fi; }

# Every invocation runs with the temporary HOME and config. No inherited CLAUDE_* or SAMEWRITE_*.
CC() { env -i HOME="$W/home" PATH="$PATH" CLAUDE_CONFIG_DIR="$CFG" "$CLAUDE" "$@"; }

newest_transcript() {
  "$PY" - "$CFG" <<'EOF'
import glob, os, sys
best, blob = 0, ""
for q in glob.glob(os.path.join(sys.argv[1], "projects", "*", "*.jsonl")):
    if os.path.getmtime(q) > best:
        best, blob = os.path.getmtime(q), q
print(blob)
EOF
}

echo "=== public acceptance: $REPO_SLUG, expecting $WANT ==="
echo "isolated HOME=$W/home  CLAUDE_CONFIG_DIR=$CFG"
echo

echo "--- [1] install from the published marketplace"
CC plugin marketplace add "$REPO_SLUG" 2>&1 | tail -1 | sed 's/^/  /'
CC plugin install samewrite@samewrite 2>&1 | tail -1 | sed 's/^/  /'

GOT=$("$PY" - "$CFG" <<'EOF'
import json, os, sys
# os.walk, NOT glob: a wildcard never descends into dot-directories and the manifest lives in
# `.claude-plugin/`, so glob reported NOT_FOUND on a perfectly healthy install. A probe that comes
# back empty is indistinguishable from a feature that is absent — suspect the probe first.
found = []
for root, dirs, files in os.walk(sys.argv[1]):
    if "plugin.json" not in files:
        continue
    try:
        d = json.load(open(os.path.join(root, "plugin.json")))
    except Exception:
        continue
    if d.get("name") == "samewrite":
        found.append(d.get("version", "?"))
print(sorted(set(found))[0] if found else "NOT_FOUND")
EOF
)
chk "installed version comes from the published repo" "$GOT" "$WANT"

echo
echo "--- [2] listing surface"
CC -p "Reply with exactly: LISTCHECK" --model claude-opus-5 >/dev/null 2>&1
TP=$(newest_transcript)
LIST=$("$PY" - "$TP" <<'EOF'
import json, sys
listing, blob = "", sys.argv[1]
if blob:
    for line in open(blob, errors="replace"):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") == "attachment":
            a = o.get("attachment") or {}
            if a.get("type") == "skill_listing":
                listing += a.get("content") or ""
low = listing.lower()
print(low.count("- samewrite:samewrite:"), low.count("- samewrite:edit-discipline:"), len(listing))
EOF
)
SW=$(echo "$LIST" | cut -d' ' -f1); ED=$(echo "$LIST" | cut -d' ' -f2); LB=$(echo "$LIST" | cut -d' ' -f3)
chk "samewrite appears in the listing exactly once" "$SW" "1"
chk "edit-discipline stays hidden (disable-model-invocation)" "$ED" "0"
echo "  MEASURED  listing is $LB bytes in this profile"

echo
echo "--- [3] the skill body loads on demand, once"
CC -p "/samewrite" --model claude-opus-5 >/dev/null 2>&1
TP=$(newest_transcript)
BODY=$("$PY" -c "
import sys
b = sys.argv[1]
print(open(b, errors='replace').read().count('Optimize **correct result per total cost**') if b else 0)
" "$TP")
chk "/samewrite loads the canonical body exactly once" "$BODY" "1"

echo
echo "--- [4] an ordinary prompt still works"
mkdir -p "$W/work/t"
printf 'def clamp(x, lo, hi):\n    return min(lo, max(hi, x))\n' > "$W/work/t/m.py"
printf 'from m import clamp\ndef test_c():\n    assert clamp(5, 0, 3) == 3\n    assert clamp(-1, 0, 3) == 0\n' > "$W/work/t/test_t.py"
( cd "$W/work/t" && env -i HOME="$W/home" PATH="$PATH" CLAUDE_CONFIG_DIR="$CFG" \
  "$CLAUDE" -p "test_t.py fails. Fix the bug." --model claude-opus-5 --permission-mode acceptEdits \
  --allowedTools "Bash(python3:*),Read,Edit,Write" >/dev/null 2>&1 )
( cd "$W/work/t" && "$PY" -m pytest -q test_t.py >/dev/null 2>&1 ) \
  && ok "ordinary coding prompt works (bug fixed, tests green)" \
  || bad "ordinary coding prompt did not fix the bug"

echo
echo "--- [5] guard install, opt-in output hook, idempotence, precise uninstall"
SRC=$("$PY" - "$CFG" <<'EOF'
import os, sys
hits = [os.path.join(r, "install.sh") for r, _d, f in os.walk(sys.argv[1])
        if "install.sh" in f and os.path.basename(r) == "hooks"]
print(sorted(hits)[0] if hits else "")
EOF
)
if [ -n "$SRC" ] && [ -f "$SRC" ]; then
  env -i HOME="$W/home" PATH="$PATH" CLAUDE_CONFIG_DIR="$CFG" bash "$SRC" >/dev/null 2>&1
  B1=$(cat "$CFG/settings.json")
  env -i HOME="$W/home" PATH="$PATH" CLAUDE_CONFIG_DIR="$CFG" bash "$SRC" >/dev/null 2>&1
  chk "guard reinstall is idempotent (settings byte-identical)" \
      "$([ "$(cat "$CFG/settings.json")" = "$B1" ] && echo same || echo diff)" "same"
  G=$("$PY" -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(sum(1 for e in d.get('hooks', {}).get('PreToolUse', [])
          for h in e.get('hooks', []) if 'write_noop_guard' in h.get('command', '')))
" "$CFG/settings.json")
  chk "exactly one guard entry" "$G" "1"
  env -i HOME="$W/home" PATH="$PATH" CLAUDE_CONFIG_DIR="$CFG" bash "$SRC" --human-output >/dev/null 2>&1
  H=$("$PY" -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(sum(1 for e in d.get('hooks', {}).get('SessionStart', []) for h in e.get('hooks', [])
          if 'samewrite' in h.get('command', '').lower()))
" "$CFG/settings.json")
  if [ "$H" -ge 1 ]; then ok "--human-output registers the opt-in SessionStart hook ($H)"
  else bad "--human-output registered nothing"; fi
  UN="$(dirname "$SRC")/uninstall.sh"
  if [ -f "$UN" ]; then
    env -i HOME="$W/home" PATH="$PATH" CLAUDE_CONFIG_DIR="$CFG" bash "$UN" >/dev/null 2>&1
    # Count samewrite's OWN hook entries only. Claude Code writes its plugin registration
    # (`enabledPlugins`, `extraKnownMarketplaces`) into the same file, and those contain the string
    # "samewrite" while belonging to the CLI, not to us — `/plugin uninstall` owns them.
    # hooks/uninstall.sh must not touch them, so counting raw string hits calls correct behaviour
    # a failure.
    LEFT=$("$PY" -c "
import json, sys
d = json.load(open(sys.argv[1]))
n = 0
for event, entries in (d.get('hooks') or {}).items():
    for e in entries or []:
        for h in e.get('hooks', []) or []:
            c = h.get('command', '')
            if 'write_noop_guard' in c or 'samewrite' in c.lower():
                n += 1
print(n)
" "$CFG/settings.json")
    chk "uninstall removes every samewrite hook entry" "$LEFT" "0"
    FOREIGN=$("$PY" -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(int(bool(d.get('enabledPlugins')) and bool(d.get('extraKnownMarketplaces'))))
" "$CFG/settings.json")
    chk "uninstall leaves the CLI's own plugin registration alone (that is /plugin's job)" \
        "$FOREIGN" "1"
  fi
else
  bad "hooks/install.sh not found inside the installed plugin"
fi

echo
echo "--- [6] plugin uninstall"
CC plugin uninstall samewrite 2>&1 | tail -1 | sed 's/^/  /'
STILL=$("$PY" - "$CFG" <<'EOF'
import json, os, sys
n = 0
for root, _d, files in os.walk(sys.argv[1]):
    if "plugin.json" not in files:
        continue
    try:
        if json.load(open(os.path.join(root, "plugin.json"))).get("name") == "samewrite":
            n += 1
    except Exception:
        pass
print(n)
EOF
)
ACTIVE=$("$PY" -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    d = {}
print(1 if any('samewrite' in str(k).lower() or 'samewrite' in json.dumps(v).lower()
               for k, v in (d.get('enabledPlugins') or {}).items()) else 0)
" "$CFG/settings.json")
chk "no samewrite plugin remains enabled after uninstall" "$ACTIVE" "0"
echo "  NOTE      $STILL cached manifest(s) remain on disk; Claude Code keeps its plugin cache by design"

rm -f "$CFG/.credentials.json"
rm -rf "$W"
echo
echo "PUBLIC ACCEPTANCE $P PASS / $F FAIL"
[ "$F" -eq 0 ]
