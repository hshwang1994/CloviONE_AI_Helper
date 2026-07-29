#!/usr/bin/env bash
# In-place upgrade (spec §30). Backs up, redeploys source, re-installs deps,
# migrates, restarts. Run as root. Source staged at STAGE.
set -euo pipefail
export LC_ALL=C.UTF-8
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

APP_DIR=/opt/clovirone-web-assistant
# Default STAGE to the stage this script was extracted into (script lives at
# <stage>/app-src/scripts/), so running the script from ANY unpacked bundle
# installs THAT bundle. A stale fixed path once silently reinstalled old code.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF_STAGE="$(cd "${SCRIPT_DIR}/../.." && pwd)"
if [ -z "${STAGE:-}" ] && [ -d "${SELF_STAGE}/app-src" ] && [ -d "${SELF_STAGE}/wheels" ]; then
  STAGE="${SELF_STAGE}"
fi
STAGE="${STAGE:-/home/cloviradmin/deploy/stage}"
echo "stage: ${STAGE}"

echo "=== upgrade start ==="
# 1. Backup first (rollback point)
if [ -x "$APP_DIR/scripts/backup-clovirone-web-assistant.sh" ]; then
  "$APP_DIR/scripts/backup-clovirone-web-assistant.sh"
fi

# 2. Stop services (worker first for graceful job drain)
systemctl stop clovirone-web-worker.service 2>/dev/null || true
systemctl stop clovirone-web-assistant.service 2>/dev/null || true

# 3. Re-run installer (idempotent — redeploys source, deps, migrate, units, nginx, start)
STAGE="$STAGE" "$STAGE/app-src/scripts/install-clovirone-web-assistant.sh"

echo "UPGRADE_OK"
