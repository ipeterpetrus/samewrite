#!/usr/bin/env bash
# Regenerate docs/FIELD_DATA.md dari ledger lapangan, commit bila berubah.
# Yang masuk repo hanya agregat: jumlah, byte, persentase. Nol path, nol isi.
set -euo pipefail
REPO="${SAMEWRITE_REPO:-$HOME/samewrite}"
LEDGERS="${SAMEWRITE_LEDGERS:-$HOME/logs/samewrite.jsonl}"
OUT="$REPO/docs/FIELD_DATA.md"

# shellcheck disable=SC2086
NEW="$(/usr/bin/python3 "$REPO/tools/report.py" $LEDGERS --markdown 2>/dev/null || true)"
[ -z "$NEW" ] && { echo "ledger kosong — tak ada yang di-feed"; exit 0; }

if [ -f "$OUT" ] && [ "$NEW" = "$(cat "$OUT")" ]; then
  echo "field data tak berubah — tak menulis, tak commit"     # samewrite pada dirinya sendiri
  exit 0
fi
printf '%s\n' "$NEW" > "$OUT"
cd "$REPO"
git add docs/FIELD_DATA.md
git diff --cached --quiet && { echo "nol perubahan ter-stage"; exit 0; }
git -c user.email="${GIT_EMAIL:-ipeterpetrus@gmail.com}" -c user.name="${GIT_NAME:-Peter Jackson}" \
    commit -q -m "field data: $(date -u +%Y-%m-%d)"
if [ "${SAMEWRITE_PUSH:-1}" = "1" ]; then
  git push -q origin HEAD && echo "field data ter-push"
else
  echo "commit dibuat, push dilewati (SAMEWRITE_PUSH=0)"
fi
