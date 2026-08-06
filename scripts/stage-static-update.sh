#!/usr/bin/env bash
# Stage a frontend-only (static asset) hot update for production.
# Builds a checksummed tarball of the given repo-relative files (text files
# LF-normalized, binaries copied byte-for-byte), then prints the exact scp +
# (user-run) sudo apply commands.
# The sudo apply step is intentionally NOT executed here — it needs the user's
# password on the server. See docs/MAINTENANCE_PLAYBOOK.md §1.
#
# Usage (from repo root):
#   scripts/stage-static-update.sh app/static/css/admin.css app/static/js/admin/app.js ...
#   scripts/stage-static-update.sh          # no args = EVERY file under app/static
#
# Why "every file under app/static" and not a hardcoded list: the old default
# named three files (admin.css, sections.js, app.js). Every asset added later —
# admin/common.js, topbar.css, theme.js, the img/ logos — was silently dropped,
# and the verify loop reused the same list so it passed without checking them.
# Discovering the tree means a new file can never be forgotten.
set -euo pipefail
export LC_ALL=C.UTF-8

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# 설치처 고유값. 기본값을 두지 않는다 - 예전엔 최초 고객사의 계정@IP 가 기본값이라, 다른
# 설치처에서 이 스크립트가 인쇄한 scp 명령을 그대로 복사하면 **남의 서버**로 파일을 밀어 넣었다.
# 이 스크립트는 명령을 인쇄만 하고 실행하지 않지만, 사람이 복사해 붙일 문자열이므로 같은 위험이다.
SERVER="${SERVER:-}"
BASE_URL="${BASE_URL:-}"
if [ -z "$SERVER" ] || [ -z "$BASE_URL" ]; then
  echo "SERVER 와 BASE_URL 을 지정해야 합니다(설치처마다 다른 값이라 기본값이 없습니다)."
  echo "예: SERVER=admin@10.0.0.10 BASE_URL=https://portal.example.internal bash $0"
  exit 2
fi
APP_DIR="/opt/clovirone-web-assistant"
REMOTE_STAGE="~/deploy-static-update"
OUT="${OUT:-dist/static-update}"   # 테스트가 임시 디렉터리로 돌릴 수 있게 열어 둔다

# Binary assets must NOT go through CRLF normalization — sed strips a byte and
# corrupts them (a PNG went 13882 → 13881 bytes). Match .gitattributes' binary set.
is_binary() {
  case "${1,,}" in
    *.png|*.ico|*.jpg|*.jpeg|*.gif|*.woff|*.woff2|*.ttf|*.otf|*.eot) return 0 ;;
    *) return 1 ;;
  esac
}

FILES=("$@")
if [ ${#FILES[@]} -eq 0 ]; then
  # Discover every file under app/static (sorted for deterministic tar/checksums).
  while IFS= read -r f; do FILES+=("$f"); done < <(find app/static -type f | LC_ALL=C sort)
fi
[ ${#FILES[@]} -gt 0 ] || { echo "FAIL: no static files found"; exit 1; }

# Validate inputs are inside app/static (safety: never ship arbitrary paths).
for f in "${FILES[@]}"; do
  [ -f "$f" ] || { echo "FAIL: not a file: $f"; exit 1; }
  case "$f" in app/static/*) : ;; *) echo "FAIL: only app/static/* allowed: $f"; exit 1;; esac
done

rm -rf "$OUT"; mkdir -p "$OUT/payload"
for f in "${FILES[@]}"; do
  mkdir -p "$OUT/payload/$(dirname "$f")"
  if is_binary "$f"; then
    cp -- "$f" "$OUT/payload/$f"                   # binary: copy byte-for-byte
  else
    sed 's/\r$//' "$f" > "$OUT/payload/$f"         # text: normalize CRLF -> LF
  fi
done

( cd "$OUT/payload"
  # shellcheck disable=SC2046
  sha256sum $(printf '%s\n' "${FILES[@]}") > ../SHA256SUMS.txt
  # shellcheck disable=SC2046
  tar -czf ../static-update.tar.gz $(printf '%s\n' "${FILES[@]}") )

echo "== staged =="
ls -l "$OUT/static-update.tar.gz" "$OUT/SHA256SUMS.txt"
echo ""
echo "== files =="; printf '  %s\n' "${FILES[@]}"
echo ""
echo "== next: copy to server (SSH key auth) =="
echo "  ssh $SERVER 'mkdir -p $REMOTE_STAGE'"
echo "  scp $OUT/static-update.tar.gz $OUT/SHA256SUMS.txt $SERVER:$REMOTE_STAGE/"
echo ""
echo "== next: apply on server (USER runs this — needs sudo password, real terminal) =="
echo "  ssh -t $SERVER 'sudo tar -xzf $REMOTE_STAGE/static-update.tar.gz -C $APP_DIR \\"
echo "     && cd $APP_DIR && sudo sha256sum -c $REMOTE_STAGE/SHA256SUMS.txt'"
echo ""
echo "== verify (no sudo): served hashes must equal local =="
# Expected hash comes from the staged payload (already normalized/copied), so
# text and binary are handled identically and can't drift from what shipped.
for f in "${FILES[@]}"; do
  rel="${f#app/static/}"
  echo "  curl -sk $BASE_URL/static/$rel | sha256sum   # expect $(sha256sum "$OUT/payload/$f" | cut -d' ' -f1)"
done
echo ""
# No hard-refresh instruction: app/core/assets.py fingerprints each asset URL by
# mtime+size, so a changed file changes its URL and the browser refetches on its
# own. Asking the user to Ctrl+Shift+R would contradict that design (CLAUDE.md §6).
echo "No browser refresh needed — assets.py fingerprints changed files into new URLs."
