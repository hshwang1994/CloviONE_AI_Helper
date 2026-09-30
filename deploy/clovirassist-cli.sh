#!/usr/bin/env bash
# `clovirassist` 명령 (계획 3.17, D-522). 설치(Stage 13)가 /usr/local/bin/clovirassist 로 깐다.
#
# 설치 뒤의 운영은 이 명령 하나를 지난다. 이 파일은 **나누기만** 한다. 일은 두 곳이 한다.
#
#   서버를 바꾸는 일(설치, 업그레이드, 되돌리기, 제거, 검증, 저장소 유닛, AI 모델)
#     → /opt/clovirassist/deploy/install.sh <같은 서브커맨드>
#   제품 안의 일(사용자, 마이그레이션, 저장소, AI 모델 점검, 첫 관리자 코드)
#     → install.sh app-cli <모듈> : 서비스 계정과 설치 환경으로 venv 의 python -m app.cli.<모듈>
#
# 두 번째 갈래도 install.sh 를 지나는 이유는 하나다. 설치 환경을 읽어 서비스 계정으로 도는 방법(run_as_app)이 그 파일
# 한 곳에만 있어야 한다. 여기서 한 벌 더 만들면 둘 중 하나만 고쳐지는 날이 온다.
set -euo pipefail

APP_DIR="${CLOVIRASSIST_APP_DIR:-/opt/clovirassist}"
INSTALLER="$APP_DIR/deploy/install.sh"

usage() {
  cat <<'EOF'
ClovirAssist 운영 명령

  sudo clovirassist <명령> [옵션]

서버
  install | upgrade | rollback | uninstall | verify | version | preflight | storage | ai
                        설치 스크립트의 같은 이름 명령이다. 옵션은 clovirassist install --help 로 봅니다
  first-admin-code      사용자가 아직 없을 때 첫 관리자 설정 코드를 새로 만든다

제품
  user <명령>           사용자 관리(add, list, show, passwd, set-role 등). clovirassist user --help
  migrate <명령>        데이터 이관 도구. clovirassist migrate --help
  storage-cli <명령>    파일 저장소 점검. clovirassist storage-cli --help
  ai-cli <명령>         임베딩 모델 점검(status, selftest). clovirassist ai-cli --help
EOF
}

[ -x "$INSTALLER" ] || { echo "설치된 ClovirAssist 를 찾을 수 없습니다($INSTALLER)." >&2; exit 1; }

command="${1:-}"
[ -n "$command" ] || { usage; exit 64; }
shift || true

case "$command" in
  install|upgrade|rollback|uninstall|verify|version|preflight|storage|ai)
    exec "$INSTALLER" "$command" "$@" ;;
  first-admin-code)
    exec "$INSTALLER" app-cli user_cli first-admin-code "$@" ;;
  user)
    exec "$INSTALLER" app-cli user_cli "$@" ;;
  migrate)
    exec "$INSTALLER" app-cli migrate_cli "$@" ;;
  storage-cli)
    exec "$INSTALLER" app-cli storage_cli "$@" ;;
  ai-cli)
    exec "$INSTALLER" app-cli ai_cli "$@" ;;
  -h|--help|help)
    usage ;;
  *)
    echo "모르는 명령입니다: $command" >&2
    usage >&2
    exit 64 ;;
esac
