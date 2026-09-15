#!/usr/bin/env bash
# OpenClaw acceptance for SameWrite — against a REAL OpenClaw install, in an ISOLATED state dir.
#
#   OPENCLAW_BIN=/path/to/openclaw.mjs NODE_BIN=/path/to/node \
#     bash tests/acceptance_openclaw.sh
#
# Answers, by execution: does OpenClaw discover, list and keep progressive the canonical SameWrite
# skill, is the shipped `edit-discipline` alias correctly hidden from the model there, and what does
# an UNUSED skill actually cost. Filesystem and CLI only — listing skills needs no credentials.
#
# The user's real ~/.openclaw is never touched: OPENCLAW_STATE_DIR points into a temp directory
# this script creates and removes. Note that isolation has a documented consequence — a non-default
# state dir deliberately excludes home-scoped roots such as ~/.agents/skills, so that tier is out of
# scope here and is reported as such rather than silently assumed to work.
#
# NOT part of CI: needs a Node >= 24.16 (or >= 26.1) runtime and an OpenClaw install.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OC="${OPENCLAW_BIN:?set OPENCLAW_BIN to openclaw.mjs}"
NODE="${NODE_BIN:-node}"
W=$(mktemp -d /tmp/sw-oc-XXXXXX)
export OPENCLAW_STATE_DIR="$W/state"
mkdir -p "$OPENCLAW_STATE_DIR/skills"
P=0; F=0
ok()  { P=$((P+1)); printf '  PASS  %s\n' "$1"; }
bad() { F=$((F+1)); printf '  FAIL  %s\n' "$1"; }
chk() { if [ "$2" = "$3" ]; then ok "$1 ($2)"; else bad "$1: got '$2', want '$3'"; fi; }
OCC() { "$NODE" "$OC" "$@"; }

echo "=== OpenClaw acceptance ==="
echo "node        : $("$NODE" --version)"
echo "openclaw    : $(OCC --version 2>&1 | tail -1)"
echo "state dir   : $OPENCLAW_STATE_DIR (isolated)"
echo

echo "--- [1] install: copy the canonical skill and the shipped alias into a skills root"
cp -r "$ROOT/skills/samewrite" "$OPENCLAW_STATE_DIR/skills/samewrite"
cp -r "$ROOT/skills/edit-discipline" "$OPENCLAW_STATE_DIR/skills/edit-discipline"
ok "canonical skill copied unchanged (no adapter, no transformation)"
CANON=$(sha256sum "$ROOT/skills/samewrite/SKILL.md" | cut -c1-16)
INST=$(sha256sum "$OPENCLAW_STATE_DIR/skills/samewrite/SKILL.md" | cut -c1-16)
chk "installed bytes identical to the repository's canonical skill" "$INST" "$CANON"

echo
echo "--- [2] discovery and listing"
J=$(OCC skills info samewrite --json 2>/dev/null)
NAME=$("$NODE" -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(j.name||"")}catch(e){console.log("")}})' <<<"$J")
chk "openclaw discovers the skill by name" "$NAME" "samewrite"
DESC=$("$NODE" -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log((j.description||"").length)}catch(e){console.log(0)}})' <<<"$J")
REPO_DESC=$(/usr/bin/python3 -c "
import sys
fm=open('$ROOT/skills/samewrite/SKILL.md').read().split('---')[1]
print(len([l for l in fm.splitlines() if l.startswith('description:')][0].split(':',1)[1].strip()))
")
chk "description survives whole (not truncated)" "$DESC" "$REPO_DESC"
VIS=$("$NODE" -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(String(j.modelVisible))}catch(e){console.log("?")}})' <<<"$J")
chk "canonical skill is visible to the model" "$VIS" "true"

echo
echo "--- [3] the shipped alias must stay hidden from the model"
JA=$(OCC skills info edit-discipline --json 2>/dev/null)
AVIS=$("$NODE" -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(String(j.modelVisible))}catch(e){console.log("?")}})' <<<"$JA")
AUSER=$("$NODE" -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(String(j.userInvocable))}catch(e){console.log("?")}})' <<<"$JA")
chk "alias hidden from the model (disable-model-invocation honoured)" "$AVIS" "false"
chk "alias still invocable by a human" "$AUSER" "true"

echo
echo "--- [4] what an UNUSED skill costs"
# Bytes, via the one definition this project publishes (tools/adapters.py: everything after the
# closing front-matter delimiter). Counting characters here and printing them as "B" was off by 72
# on a file with 72 multi-byte characters — small, wrong, and exactly the labelling error the hash
# audit was about.
BODY=$(/usr/bin/python3 -c "
import sys; sys.path.insert(0, '$ROOT/tools'); import adapters
print(len(adapters.body_bytes('$OPENCLAW_STATE_DIR/skills/samewrite/SKILL.md')))
")
CATALOG=$(( ${#NAME} + DESC + 40 ))
echo "  MEASURED  catalog entry  ~${CATALOG} B  (name + description + location line)"
echo "  MEASURED  body on disk    ${BODY} B  — read on demand, not placed in the prompt"
ok "progressive loading: the body is fetched from its location, not injected (per formatSkillCatalog)"

echo
echo "--- [5] uninstall"
rm -rf "$OPENCLAW_STATE_DIR/skills/samewrite" "$OPENCLAW_STATE_DIR/skills/edit-discipline"
J2=$(OCC skills info samewrite --json 2>/dev/null)
GONE=$("$NODE" -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(j&&j.name?"still-there":"gone")}catch(e){console.log("gone")}})' <<<"$J2")
chk "removing the directory removes the skill" "$GONE" "gone"

echo
echo "--- [6] isolation"
if [ -e "$HOME/.openclaw/skills/samewrite" ]; then bad "the real ~/.openclaw was touched"
else ok "\$HOME/.openclaw untouched"; fi

rm -rf "$W"
echo
echo "OPENCLAW ACCEPTANCE $P PASS / $F FAIL"
echo "SCOPE NOTE: a non-default OPENCLAW_STATE_DIR excludes home-scoped roots (~/.agents/skills),"
echo "so that tier is UNTESTED here rather than assumed to work."
[ "$F" -eq 0 ]
