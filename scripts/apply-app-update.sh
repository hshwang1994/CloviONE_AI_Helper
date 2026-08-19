#!/usr/bin/env bash
# 정적 자산이 아닌 앱 파일(Jinja 템플릿·Python 모듈)을 TEST SERVER 에 적용하고 재시작한다.
#
# ## `apply-static-update.sh` 와 무엇이 다른가
#
# 정적 자산은 재시작이 필요 없다(`assets.py` 가 mtime+size 로 URL 을 지문화해 브라우저가
# 알아서 다시 받는다). 반면 템플릿과 파이썬 모듈은 **프로세스 안에 로드돼 있어서** 파일만
# 바꾸면 아무 일도 일어나지 않는다 — "배포했는데 화면이 그대로다"는 이 저장소가 실제로
# 여러 번 헛돈 자리다. 그래서 이 스크립트는 재시작과 **health gate** 까지 한다.
#
# ## 안전장치
#
#   1. 대상 파일을 서버에서 `.bak-<타임스탬프>` 로 백업한다.
#   2. `.py` 는 서버에서 `py_compile` 로 문법을 먼저 확인한다(깨진 파일로 재시작하지 않는다).
#   3. 재시작 후 `/readyz` 가 200 이 될 때까지 최대 10회 확인한다.
#   4. 실패하면 **백업으로 되돌리고 다시 재시작한 뒤** 0이 아닌 코드로 끝난다.
#
# ## 자격증명 (CLAUDE.md 불변규칙 3)
#
# `dist/ops/server.env`(gitignore)에서만 읽는다. 원격 스크립트는 **파일로 전송**하고
# 비밀번호는 그 스크립트의 **stdin 첫 줄**로만 건넨다 — 명령행에도, 원격 파일에도, 로그에도
# 남지 않는다. (`ssh ... 'bash -s' <<HEREDOC` 는 쓸 수 없다: 그러면 스크립트 자체가 stdin 을
# 차지해 비밀번호를 넣을 자리가 없다. 실제로 그렇게 썼다가 `read` 가 스크립트 한 줄을
# 삼켰다.)
#
# ## 쓰는 법
#
#   bash scripts/apply-app-update.sh app/templates_html/login.html [...]
set -uo pipefail
export LC_ALL=C.UTF-8

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

[ $# -gt 0 ] || { echo "FAIL: 적용할 파일을 하나 이상 지정해야 한다 (기본값 없음)"; exit 2; }

ENV_FILE="${CLOVIR_OPS_ENV:-dist/ops/server.env}"
[ -f "$ENV_FILE" ] || { echo "FAIL: $ENV_FILE 가 없다"; exit 2; }
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${SERVER:?}"; : "${BASE_URL:?}"; : "${SUDO_PW:?}"

APP_DIR="/opt/clovirone-web-assistant"
SERVICE="clovirone-web-assistant.service"
REMOTE_STAGE="deploy-app-update"
OUT="dist/app-update"
TS="$(date +%Y%m%d_%H%M%S)"

for f in "$@"; do
  [ -f "$f" ] || { echo "FAIL: not a file: $f"; exit 1; }
  case "$f" in
    app/static/*) echo "FAIL: 정적 자산은 apply-static-update.sh 를 써라: $f"; exit 1 ;;
    app/*) : ;;
    *) echo "FAIL: app/ 아래 파일만 허용한다: $f"; exit 1 ;;
  esac
done

echo "== stage =="
rm -rf "$OUT"; mkdir -p "$OUT/payload"
for f in "$@"; do
  mkdir -p "$OUT/payload/$(dirname "$f")"
  sed 's/\r$//' "$f" > "$OUT/payload/$f"
done
( cd "$OUT/payload" && tar -czf ../app-update.tar.gz "$@" )
printf '  %s\n' "$@"

# 원격 실행 스크립트. 파일 목록·타임스탬프만 여기서 박고 나머지는 그대로 원격에서 돈다.
cat > "$OUT/remote.sh" <<REMOTE
#!/usr/bin/env bash
set -uo pipefail
read -r PW
S() { printf '%s\n' "\$PW" | sudo -S -p '' "\$@"; }

APP_DIR="$APP_DIR"
SERVICE="$SERVICE"
TS="$TS"
FILES="$*"

cd "\$APP_DIR" || exit 1

echo "[1/5] backup"
for f in \$FILES; do
  if [ -f "\$f" ]; then S cp -a "\$f" "\$f.bak-\$TS" || exit 1; fi
done

echo "[2/5] extract"
S tar -xzf ~/$REMOTE_STAGE/app-update.tar.gz -C "\$APP_DIR" || exit 1

echo "[3/5] syntax gate"
for f in \$FILES; do
  case "\$f" in
    *.py)
      PYTHONPYCACHEPREFIX=/tmp/pyc-\$\$ "\$APP_DIR/venv/bin/python3" -m py_compile "\$f" || {
        echo "SYNTAX_FAIL \$f"; exit 3; }
      ;;
  esac
done

echo "[4/5] restart \$SERVICE"
S systemctl restart "\$SERVICE"

echo "[5/5] health gate"
ok=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  code="\$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/readyz 2>/dev/null || true)"
  if [ "\$code" = "200" ]; then ok=1; break; fi
done
if [ "\$ok" != "1" ]; then
  echo "HEALTH_FAIL — 롤백한다"
  for f in \$FILES; do
    if [ -f "\$f.bak-\$TS" ]; then S cp -a "\$f.bak-\$TS" "\$f"; fi
  done
  S systemctl restart "\$SERVICE"
  exit 4
fi
echo "APP_UPDATE_OK"
REMOTE

echo "== copy =="
ssh -o BatchMode=yes "$SERVER" "mkdir -p ~/$REMOTE_STAGE" || exit 1
scp -q "$OUT/app-update.tar.gz" "$OUT/remote.sh" "$SERVER:~/$REMOTE_STAGE/" || exit 1

echo "== backup + apply + restart + health gate =="
printf '%s\n' "$SUDO_PW" | ssh -o BatchMode=yes "$SERVER" "bash ~/$REMOTE_STAGE/remote.sh" 2>&1 \
  | grep -v '^\[sudo\]'
RC=${PIPESTATUS[1]}
if [ "$RC" != "0" ]; then
  echo "APP_UPDATE_FAILED (rc=$RC)"
  exit 1
fi

echo "== verify (외부에서 실제로 뜨는가) =="
CODE="$(curl -sk -o /dev/null -w '%{http_code}' --max-time 20 "$BASE_URL/login")"
echo "  GET $BASE_URL/login -> $CODE"
[ "$CODE" = "200" ] || { echo "APP_UPDATE_FAILED (로그인 화면이 200 이 아니다)"; exit 1; }
echo "APP_UPDATE_OK"
