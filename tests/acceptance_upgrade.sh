#!/usr/bin/env bash
# PRE-MERGE LOCAL PLUGIN ACCEPTANCE + UPGRADE 1.0.0 -> the CANDIDATE in this worktree.
# The candidate's version is read from .claude-plugin/plugin.json, never hardcoded: a script that
# prints a version it did not actually test is the same stale-claim defect it exists to catch.
# NOT part of CI: needs a logged-in Claude Code CLI and spends five small model calls. Run by hand
# before a release:   SAMEWRITE_CRED=<your config dir>/.credentials.json bash tests/acceptance_upgrade.sh
# Fresh HOME + CLAUDE_CONFIG_DIR; never the developer profile. Only the credentials file is copied
# (cp, never read) so `claude -p` can run; it is deleted at the end.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W=$(mktemp -d /tmp/sw-accept-XXXXXX)
HOME_REAL="$HOME"
CFG="$W/cfg"; mkdir -p "$CFG" "$W/work" "$W/bin"
CRED="${SAMEWRITE_CRED:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.credentials.json}"   # copied, never read; deleted at the end
cp "$CRED" "$CFG/.credentials.json" && chmod 600 "$CFG/.credentials.json"
cat > "$CFG/settings.json" <<'EOF'
{"statusLine":{"type":"command","command":"bash /p/hooks/ponytail-statusline.sh"},
 "someUserKey":{"nested":[1,2,3]},
 "hooks":{"SessionStart":[{"matcher":"startup|resume|clear|compact","hooks":[{"type":"command","command":"node /p/hooks/ponytail-activate.js"}]}],
          "PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"rtk hook claude"}]}]}}
EOF
PY=/usr/bin/python3
CAND=$("$PY" -c "import json;print(json.load(open('$REPO/.claude-plugin/plugin.json'))['version'])")
FSHA() { $PY -c "
import json,hashlib; d=json.load(open('$CFG/settings.json'))
for k in ('enabledPlugins','extraKnownMarketplaces'): d.pop(k, None)   # Claude Code's own plugin bookkeeping
for ev in list(d.get('hooks',{})):
    d['hooks'][ev]=[dict(m,hooks=[h for h in m['hooks'] if 'write_noop_guard.py' not in h['command'] and 'samewrite-output-hook' not in h['command']]) for m in d['hooks'][ev]]
    d['hooks'][ev]=[m for m in d['hooks'][ev] if m['hooks']]
print(hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest())"; }
FOREIGN_SHA=$(FSHA)
CL="$HOME_REAL/.local/bin/claude"
run() { env -i HOME="$W" PATH="$PATH" CLAUDE_CONFIG_DIR="$CFG" "$CL" "$@"; }
pass=0; fail=0
check() { if [ "$2" = "$3" ]; then pass=$((pass+1)); echo "  PASS  $1"; else fail=$((fail+1)); echo "  FAIL  $1: got '$2' want '$3'"; fi; }
listing() {
  local d="$W/work/$1"; mkdir -p "$d"; printf 'def f():\n    return 1\n' > "$d/m.py"
  (cd "$d" && run -p "Reply with exactly: OK" --model claude-haiku-4-5-20251001 >/dev/null 2>&1)
  local tp; tp=$(ls -t "$CFG"/projects/*/*.jsonl 2>/dev/null | head -1)
  $PY - "$tp" <<'PYX'
import json,sys
lst=""
for l in open(sys.argv[1],errors="replace"):
    try: o=json.loads(l)
    except Exception: continue
    if o.get("type")=="attachment" and (o.get("attachment") or {}).get("type")=="skill_listing": lst+=o["attachment"]["content"]
# plugin skills are listed namespaced: "- samewrite:samewrite:" / "- samewrite:edit-discipline:"
print("samewrite=%d edit-discipline=%d bytes=%d" % (lst.count("- samewrite:samewrite:") + lst.count("- samewrite: "),
                                                     lst.count("- samewrite:edit-discipline:") + lst.count("- edit-discipline:"), len(lst)))
PYX
}
GUARD_N() { $PY -c "import json;d=json.load(open('$CFG/settings.json'));print(sum('write_noop_guard.py' in h['command'] for m in d['hooks'].get('PreToolUse',[]) for h in m['hooks']))"; }
INST() { env HOME="$W" CLAUDE_CONFIG_DIR="$CFG" SAMEWRITE_DST="$W/bin/write_noop_guard.py" SAMEWRITE_LEDGER="$W/ledger.jsonl" SAMEWRITE_PYTHON=$PY bash "$@"; }

echo "=== [1] 1.0.0 baseline (worktree of main = 0aec7ce as a local marketplace)"
mkdir -p "$W/v100" && (cd "$REPO" && git archive 0aec7ce) | tar -x -C "$W/v100" && (cd "$W/v100" && git init -q && git add -A && git -c user.name=a -c user.email=a@b commit -qm "1.0.0 snapshot")
run plugin marketplace add "$W/v100" 2>&1 | tail -1 | sed 's/^/  /'
run plugin install samewrite@samewrite 2>&1 | tail -1 | sed 's/^/  /'
L0=$(listing base100); echo "  listing 1.0.0: $L0"
check "1.0.0: edit-discipline listed, samewrite absent" "$(echo "$L0" | cut -d' ' -f1,2)" "samewrite=0 edit-discipline=1"
INST "$W/v100/hooks/install.sh" >/dev/null 2>&1; echo "  1.0.0 install.sh rc=$?"
check "1.0.0: one guard entry (old quoted form)" "$(GUARD_N)" "1"

echo "=== [2] upgrade to candidate $CAND (marketplace re-pointed at the branch checkout)"
run plugin marketplace remove samewrite >/dev/null 2>&1 || true
run plugin marketplace add "$REPO" 2>&1 | tail -1 | sed 's/^/  /'
run plugin install samewrite@samewrite 2>&1 | tail -1 | sed 's/^/  /'
check "upgrade: exactly one samewrite plugin" "$(run plugin list 2>&1 | grep -c 'samewrite@samewrite')" "1"
L1=$(listing up110); echo "  listing $CAND: $L1"
check "upgrade: samewrite listed once, edit-discipline hidden" "$(echo "$L1" | cut -d' ' -f1,2)" "samewrite=1 edit-discipline=0"
INST "$REPO/hooks/install.sh" 2>&1 | grep -E "sudah terpasang|ditambahkan|GAGAL|BATAL" | sed "s|^|  $CAND install.sh: |"
check "upgrade: still one guard entry (1.0.0 form recognised, no duplicate)" "$(GUARD_N)" "1"
B1=$(cat "$CFG/settings.json"); INST "$REPO/hooks/install.sh" >/dev/null 2>&1
check "candidate reinstalled: settings byte-identical (idempotent)" "$([ "$(cat "$CFG/settings.json")" = "$B1" ] && echo same || echo diff)" "same"
INST "$REPO/hooks/install.sh" --human-output --no-guard 2>&1 | grep -E "SessionStart|GAGAL|BATAL" | sed 's/^/  --human-output: /'
NOUT=$($PY -c "import json;d=json.load(open('$CFG/settings.json'));print(sum(h['command'].endswith('# samewrite-output-hook') for m in d['hooks'].get('SessionStart',[]) for h in m['hooks']))")
check "--human-output: one SessionStart output hook" "$NOUT" "1"
FSHA_AFTER=$(FSHA)
check "foreign hooks/statusLine/custom key structurally intact after upgrade + hooks" "$FSHA_AFTER" "$FOREIGN_SHA"

echo "=== [3] behaviour on the upgraded config"
d="$W/work/fix"; mkdir -p "$d"; printf 'def clamp(x, lo, hi):\n    return min(lo, max(hi, x))\n' > "$d/mod.py"
printf 'from mod import clamp\ndef test_clamp():\n    assert clamp(5, 0, 3) == 3\n' > "$d/test_target.py"
(cd "$d" && run -p "test_target.py fails. Fix the bug." --model claude-haiku-4-5-20251001 --permission-mode acceptEdits --allowedTools "Read,Edit,Write,Bash(python3:*)" >"$d/out.txt" 2>&1)
check "ordinary coding prompt works (bug fixed)" "$(grep -c 'min(hi, max(lo, x))\|max(lo, min(hi, x))' "$d/mod.py")" "1"
TP=$(ls -t "$CFG"/projects/*/*.jsonl | head -1)
check "output hook injected exactly once in that session" "$(grep -c 'Lead with the result, blocker, or next action' "$TP")" "1"
d2="$W/work/slash"; mkdir -p "$d2"; cp "$d/mod.py" "$d2/"
(cd "$d2" && run -p "/samewrite what does this skill require before editing? answer in one line" --model claude-haiku-4-5-20251001 >"$d2/out.txt" 2>&1)
TP2=$(ls -t "$CFG"/projects/*/*.jsonl | head -1)
check "/samewrite loads the canonical body exactly once" "$(grep -c 'expand only to answer an open question' "$TP2")" "1"
d3="$W/work/alias"; mkdir -p "$d3"
(cd "$d3" && run -p "/edit-discipline one line: what is the rule?" --model claude-haiku-4-5-20251001 >"$d3/out.txt" 2>&1)
TP3=$(ls -t "$CFG"/projects/*/*.jsonl | head -1)
check "/edit-discipline alias still invocable (body loaded)" "$(grep -c 'Deprecated alias' "$TP3")" "1"

echo "=== [4] uninstall precision"
env HOME="$W" CLAUDE_CONFIG_DIR="$CFG" SAMEWRITE_DST="$W/bin/write_noop_guard.py" SAMEWRITE_PYTHON=$PY bash "$REPO/hooks/uninstall.sh" 2>&1 | tail -2 | sed 's/^/  /'
FSHA_UN=$($PY -c "
import json,hashlib; d=json.load(open('$CFG/settings.json'))
for k in ('enabledPlugins','extraKnownMarketplaces'): d.pop(k, None)
print(hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest())")
check "uninstall: settings == original foreign settings (both samewrite entries removed, nothing else)" "$FSHA_UN" "$FOREIGN_SHA"
run plugin uninstall samewrite@samewrite 2>&1 | tail -1 | sed 's/^/  /'
check "plugin uninstalled" "$(run plugin list 2>&1 | grep -c 'samewrite@samewrite')" "0"
rm -f "$CFG/.credentials.json"
echo; echo "ACCEPTANCE $pass PASS / $fail FAIL  (workdir $W)"
[ "$fail" = 0 ]
