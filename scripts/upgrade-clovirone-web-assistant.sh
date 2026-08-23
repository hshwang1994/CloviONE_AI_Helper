#!/usr/bin/env bash
# In-place upgrade (spec §30). Backs up, redeploys source, re-installs deps,
# migrates, restarts. Run as root. Source staged at STAGE.
#
# DEPLOY-01/DEPLOY-02: 예전 버전은 installer 가 요구하는 DNS_NAME/BIND_IP 를 넘기지
# 않아 installer 가 즉시 exit 2 로 죽었는데, 그 시점엔 이미 두 서비스를 정지시킨
# 뒤였고 되살리는 코드가 없어 서비스가 멈춘 채 남았다. git 경로(update-from-git.sh)에는
# 이미 backup -> install -> verify -> 실패 시 rollback_now 골격이 있었는데 번들 경로에만
# 없었다 - 여기서 같은 골격을 그대로 들여온다.
set -euo pipefail
export LC_ALL=C.UTF-8
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

APP_DIR=/opt/clovirone-web-assistant
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# installer 가 요구하는 설치처 고유값(install-clovirone-web-assistant.sh:43-52 - 다른 곳에서
# 그냥 실행하면 남의 이름으로 인증서를 만들고 없는 주소에 바인딩하는 사고를 막으려고 일부러
# 기본값을 두지 않는다). 업그레이드는 이미 설치된 서버를 대상으로 하므로 **최초 설치와 같은
# 값**을 넘겨야 한다 - 최초 설치 로그(install.log)나 nginx vhost(server_name)에서 확인할 수 있다.
DNS_NAME="${DNS_NAME:-}"
BIND_IP="${BIND_IP:-}"
if [ -z "$DNS_NAME" ] || [ -z "$BIND_IP" ]; then
  echo "DNS_NAME 과 BIND_IP 를 지정해야 합니다(설치 스크립트가 씁니다 - 최초 설치와 같은 값)."
  echo "예: DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 bash $0"
  echo "이 서버에 이미 설치돼 있다면: grep server_name /etc/nginx/sites-available/clovirone-web-assistant"
  exit 2
fi

# Default STAGE to the stage this script was extracted into (script lives at
# <stage>/app-src/scripts/), so running the script from ANY unpacked bundle
# installs THAT bundle. A stale fixed path once silently reinstalled old code.
SELF_STAGE="$(cd "${SCRIPT_DIR}/../.." && pwd)"
if [ -z "${STAGE:-}" ] && [ -d "${SELF_STAGE}/app-src" ] && [ -d "${SELF_STAGE}/wheels" ]; then
  STAGE="${SELF_STAGE}"
fi
STAGE="${STAGE:-/home/cloviradmin/deploy/stage}"
echo "stage: ${STAGE}"

# 롤백에 필요한 상태. 아직 아무것도 안 했다는 뜻으로 비워 둔다.
BACKUP_DIR=""

say() { echo "$*"; }
hr()  { echo "------------------------------------------------------------"; }

# ── 되돌리기 ────────────────────────────────────────────────────────────────
# installer 의 4단계(rsync --delete)가 백업보다 먼저 $APP_DIR 의 코드를 새 버전으로
# 덮어쓰므로, 실패 시 "그냥 서비스를 다시 켠다"만으로는 새(깨진) 코드로 재기동하게 된다.
# 반드시 백업(app.tar.gz 에 옛 코드가 통째로 들어 있다)까지 복원해야 한다.
rollback_now() {
  local why="$1"
  echo ""
  hr
  say "업그레이드 실패: $why"
  say "되돌립니다."
  hr
  if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    say "복원 중: $BACKUP_DIR"
    if bash "$STAGE/app-src/scripts/rollback-clovirone-web-assistant.sh" "$BACKUP_DIR"; then
      say "UPGRADE_ROLLED_BACK $BACKUP_DIR"
      exit 30
    fi
    say "[FAIL] 자동 복원이 끝나지 못했습니다. 서비스가 내려가 있을 수 있습니다."
    say "       확인: systemctl status clovirone-web-assistant"
    say "       재시도: bash $STAGE/app-src/scripts/rollback-clovirone-web-assistant.sh $BACKUP_DIR"
    exit 40
  fi
  say "백업이 없어 되돌릴 지점이 없습니다. 옛 코드가 남아 있는 상태로 서비스를 다시 올립니다."
  systemctl start clovirone-web-assistant.service 2>/dev/null || true
  systemctl start clovirone-web-worker.service 2>/dev/null || true
  exit 30
}

echo "=== upgrade start ==="

# ── 1. 백업 먼저(되돌릴 지점) ────────────────────────────────────────────────
# 되돌릴 지점이 없으면 진행하지 않는다 - 실패했을 때 "그냥 서비스가 멈춘 채 남는" 원래
# 사고를 되풀이하지 않으려면, 백업이 안 됐다는 것 자체를 여기서 걸러야 한다.
if [ -x "$APP_DIR/scripts/backup-clovirone-web-assistant.sh" ]; then
  BACKUP_OUT="$(bash "$APP_DIR/scripts/backup-clovirone-web-assistant.sh" 2>&1 || true)"
  printf '%s\n' "$BACKUP_OUT"
  BACKUP_DIR="$(printf '%s\n' "$BACKUP_OUT" | sed -n 's/^BACKUP_OK //p' | tail -1)"
fi
if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
  BACKUP_DIR=""
  say "백업이 만들어지지 않았습니다(최초 설치라 $APP_DIR/scripts 가 아직 없을 수 있습니다)."
  say "되돌릴 지점 없이 진행하지 않습니다."
  exit 5
fi
say "되돌릴 지점: $BACKUP_DIR"

# ── 2. 서비스 정지(worker 먼저 - 진행 중인 잡을 마치게 한다) ─────────────────
systemctl stop clovirone-web-worker.service 2>/dev/null || true
systemctl stop clovirone-web-assistant.service 2>/dev/null || true

# ── 3. 재설치(멱등 - 원본 재배포 + 의존성 + 마이그레이션 + 유닛 + nginx + 기동) ──
say "설치..."
if ! DNS_NAME="$DNS_NAME" BIND_IP="$BIND_IP" STAGE="$STAGE" \
     "$STAGE/app-src/scripts/install-clovirone-web-assistant.sh"; then
  rollback_now "설치 스크립트가 실패했습니다"
fi

# ── 4. 검증 ─────────────────────────────────────────────────────────────────
# 우리 서비스만 본다 - 같은 서버의 다른 서비스까지 판정에 넣으면, 그것들이
# 없거나 죽은 설치에서는 우리와 무관한 이유로 멀쩡한 업그레이드가 롤백된다.
say "검증..."
VERIFY_FAIL=""
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 || VERIFY_FAIL="healthz 응답 없음"
if [ -z "$VERIFY_FAIL" ]; then
  # readyz 는 DB 까지 본다 - 마이그레이션이 어긋났을 때 healthz 만으로는 안 걸린다.
  curl -fsS http://127.0.0.1:8080/readyz >/dev/null 2>&1 || VERIFY_FAIL="readyz 실패(DB 또는 마이그레이션)"
fi
if [ -z "$VERIFY_FAIL" ]; then
  systemctl is-active --quiet clovirone-web-assistant.service || VERIFY_FAIL="web 서비스가 active 가 아님"
fi
if [ -z "$VERIFY_FAIL" ]; then
  systemctl is-active --quiet clovirone-web-worker.service || VERIFY_FAIL="worker 서비스가 active 가 아님"
fi
if [ -n "$VERIFY_FAIL" ]; then
  journalctl -u clovirone-web-assistant -n 50 --no-pager 2>/dev/null || true
  rollback_now "$VERIFY_FAIL"
fi

hr
say "[OK ] healthz / readyz / web / worker"
say "이전 버전으로 되돌리려면:"
say "  bash $APP_DIR/scripts/rollback-clovirone-web-assistant.sh $BACKUP_DIR"
hr
echo "UPGRADE_OK"
