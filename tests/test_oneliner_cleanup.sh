#!/usr/bin/env bash
# The published OpenClaw one-liner must not leave a temp directory behind — on ANY outcome.
#
#   bash tests/test_oneliner_cleanup.sh
#
# An install command that litters /tmp on failure is a small bug with a long tail: the user retries
# three times, three trees of source stay on disk, and nothing ever says so. This runs the exact
# command shape published in README against a local file:// tarball and a stub `openclaw`, forcing
# each failure mode in turn, and checks that the temp directory is gone every time.
#
# Offline and deterministic: no network, no real OpenClaw, no writes outside its own temp area.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W=$(mktemp -d /tmp/sw-oneliner-XXXXXX)
trap 'rm -rf "$W"' EXIT
P=0; F=0
ok()  { P=$((P+1)); printf '  PASS  %s\n' "$1"; }
bad() { F=$((F+1)); printf '  FAIL  %s\n' "$1"; }

VER=$(/usr/bin/python3 -c "import json;print(json.load(open('$ROOT/.claude-plugin/plugin.json'))['version'])")

# The tarball GitHub would serve for this tag, built the same way, from the candidate commit.
git -C "$ROOT" archive --format=tar.gz --prefix="samewrite-$VER/" -o "$W/release.tar.gz" HEAD

# A stub `openclaw` that records what it was handed. `$1 $2` = `skills install`.
mkdir -p "$W/bin"
cat > "$W/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
[ "${OC_FAIL:-0}" = "1" ] && { echo "openclaw: simulated install failure" >&2; exit 1; }
echo "$3" > "$OC_RECORD"
exit 0
STUB
chmod +x "$W/bin/openclaw"
export PATH="$W/bin:$PATH"
export OC_RECORD="$W/record"

# The command under test, byte-for-byte the shape README publishes, with the URL as a parameter so
# the failure modes can be forced without a network.
run_oneliner() {  # $1 = url
  (d=$(mktemp -d "$W/tmp.XXXXXX") && trap 'rm -rf "$d"' EXIT \
     && curl -fsSL "$1" | tar -xz -C "$d" \
     && openclaw skills install "$d"/samewrite-*/skills/samewrite)
}
leftovers() { ls -d "$W"/tmp.* 2>/dev/null | wc -l | tr -d ' '; }

echo "=== OpenClaw one-liner cleanup safety ==="
echo "version     : $VER"
echo "archive     : $(stat -c%s "$W/release.tar.gz") B"
echo

echo "--- [1] download failure (URL does not resolve)"
run_oneliner "file://$W/does-not-exist.tar.gz" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && ok "command reports failure (rc=$rc)" || bad "download failure went unreported (rc=0)"
[ "$(leftovers)" = "0" ] && ok "no temp directory left behind" || bad "leaked $(leftovers) temp dir(s)"

echo
echo "--- [2] extract failure (URL resolves, payload is not a tarball)"
echo "this is not a gzip stream" > "$W/garbage.tar.gz"
run_oneliner "file://$W/garbage.tar.gz" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && ok "command reports failure (rc=$rc)" || bad "corrupt payload went unreported (rc=0)"
[ "$(leftovers)" = "0" ] && ok "no temp directory left behind" || bad "leaked $(leftovers) temp dir(s)"

echo
echo "--- [3] install failure (archive is fine, the host refuses)"
OC_FAIL=1 run_oneliner "file://$W/release.tar.gz" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && ok "command reports failure (rc=$rc)" || bad "install failure went unreported (rc=0)"
[ "$(leftovers)" = "0" ] && ok "no temp directory left behind" || bad "leaked $(leftovers) temp dir(s)"

echo
echo "--- [4] success"
rm -f "$OC_RECORD"
run_oneliner "file://$W/release.tar.gz" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && ok "command succeeds (rc=0)" || bad "success path failed (rc=$rc)"
[ "$(leftovers)" = "0" ] && ok "no temp directory left behind" || bad "leaked $(leftovers) temp dir(s)"
GOT=$(cat "$OC_RECORD" 2>/dev/null || echo MISSING)
case "$GOT" in
  */samewrite-$VER/skills/samewrite) ok "the glob resolved to the skill directory of THIS version" ;;
  *)                                 bad "openclaw was handed '$GOT'" ;;
esac
# The glob must not expand to two paths — that would hand OpenClaw a stray argument silently.
WORDS=$(printf '%s\n' "$GOT" | wc -w | tr -d ' ')
[ "$WORDS" = "1" ] && ok "the glob resolved to exactly one path" || bad "glob resolved to $WORDS paths"

echo
echo "--- [5] the parent shell's own EXIT trap is untouched"
# A bare `trap ... EXIT` pasted into an interactive shell would clobber whatever the user had set
# and fire only when the terminal closes. The subshell is what keeps this local.
OUT=$(trap 'echo PARENT_TRAP_STILL_MINE' EXIT; run_oneliner "file://$W/release.tar.gz" >/dev/null 2>&1; trap -p EXIT)
case "$OUT" in
  *PARENT_TRAP_STILL_MINE*) ok "caller's EXIT trap survives the install command" ;;
  *)                        bad "the install command clobbered the caller's EXIT trap" ;;
esac

echo
echo "$P PASS / $F FAIL"
[ "$F" -eq 0 ]
