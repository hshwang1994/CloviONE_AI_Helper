#!/usr/bin/env bash
# Release 설치 리허설 (계획 3.17 I3, D-522 · D-523).
#
#   sudo bash scripts/release_rehearsal.sh <assets-dir> <tag-a> <tag-b> [container-name]
#
# <assets-dir>/<tag>/ 에 `scripts/build-bundle.sh --release <tag>` 가 만든 세 파일(묶음, install.sh, SHA256SUMS)이 있어야
# 한다. 호스트에 임시 HTTPS 미러를 띄우고(openssl s_server, 자체 서명 인증서를 컨테이너가 믿게 한다) 새 Ubuntu 24.04
# 컨테이너에서 사용자가 하는 그대로 돌린다:
#
#   Release 페이지에서 install.sh 하나 받기 → preflight → install(태그를 주지 않는다 - 파일에 적힌 태그) →
#   clovirassist version · verify → 첫 관리자 만들기(설정 코드) → 메일 연결 확인(컨테이너 안의 시험용 SMTP) →
#   바깥 프록시 뒤 AI 연결 확인(tinyproxy, 가짜 키라 거절되지만 요청이 프록시를 지났는지 본다) → 프록시 해제 →
#   같은 설치 다시 돌리기 → 바뀐 묶음으로 업그레이드 시도(멈춰야 한다) → 다음 태그로 업그레이드 → 되돌리기 → 제거
#
# ── 증명하는 것과 증명하지 않는 것 ─────────────────────────────────────────────
# **증명한다**: Release 경로가 Clean 24.04 에서 끝까지 돈다 · 받은 묶음은 체크섬이 맞아야만 풀린다 · 설치 코드가 로그에
# 안 남고 첫 관리자를 만든다 · clovirassist 명령이 설치, 검증, 업그레이드, 되돌리기, 제거를 한다 · 메일 연결 확인이 잡으로
# 돈다 · 프록시 드롭인이 AI 연결 확인의 바깥 요청을 프록시로 보낸다.
# **증명하지 않는다**(R15): GitHub 의 실제 Release 다운로드(미러가 대신한다) · 실제 AI 키와 ChatGPT 계정 연결(사람의 자격이
# 필요하다) · 실제 메일 서버 · 진짜 커널 재부팅 · NFS/SMB(lxd_rehearsal.sh 머리말과 같다).
#
# 비밀 값을 출력하지 않는다. 첫 관리자 설정 코드와 관리자 비밀번호는 변수에만 두고, 설치 출력을 찍을 때 코드 줄을 가린다.
set -uo pipefail
export LC_ALL=C.UTF-8

ASSETS="${1:-}"; TAG_A="${2:-}"; TAG_B="${3:-}"; CT="${4:-release-rehearsal}"
[ -d "$ASSETS/$TAG_A" ] && [ -d "$ASSETS/$TAG_B" ] \
  || { echo "사용법: sudo bash $0 <assets-dir> <tag-a> <tag-b> [container]"; exit 64; }
command -v lxc >/dev/null 2>&1 || { echo "lxc 가 없습니다"; exit 64; }
DNS_NAME="${DNS_NAME:-clovirassist.rehearsal.invalid}"
PORT=8443
STEP=0; FAILED=0; declare -a SUMMARY=()
banner() { STEP=$((STEP+1)); echo; echo "═══ [$STEP] $* ═══"; }
ok()  { echo "[OK ] $1"; SUMMARY+=("OK   $1"); }
bad() { echo "[FAIL] $1"; SUMMARY+=("FAIL $1"); FAILED=1; }
expect_in() { if grep -qF -- "$2" <<<"$1"; then ok "$3"; else bad "$3 — 기대한 «$2» 가 없다"; fi; }
expect_not() { if grep -qF -- "$2" <<<"$1"; then bad "$3 — 나오면 안 되는 «$2» 가 있다"; else ok "$3"; fi; }
# JSON 응답은 공백 없이 온다(`"ok":true`). 모양에 기대지 않게 정규식으로 본다.
expect_re() { if grep -qE -- "$2" <<<"$1"; then ok "$3"; else bad "$3 — 기대한 /$2/ 가 없다"; fi; }
cx()  { lxc exec "$CT" -- bash -lc "$1" </dev/null 2>&1 | tr -d '\r'; }
mask() { sed -E 's/(설정 코드: ).*/\1****/; s/^code=.*/code=****/'; }
# 유닛을 다시 띄운 뒤 웹이 실제로 답할 때까지 기다린다. 기다리지 않으면 그 사이의 저장 요청이 nginx 의 502 로 조용히 사라진다
# (첫 리허설이 그렇게 AI 설정 저장을 잃고 「미설정」으로 연결 확인을 했다).
restart_units() {
  cx 'for u in clovirassist-worker clovirassist-worker-conversational clovirassist-scheduler clovirassist-web; do systemctl restart $u; done
      for _ in $(seq 1 60); do curl -fsS -o /dev/null http://127.0.0.1:8080/readyz && break; sleep 1; done; echo restarted' | tail -1
}

# ── 미러 ──────────────────────────────────────────────────────────────────────
banner "호스트에 HTTPS 미러를 띄운다"
BRIDGE_IP="$(ip -4 -o addr show lxdbr0 | awk '{print $4}' | cut -d/ -f1 | head -1)"
[ -n "$BRIDGE_IP" ] || { echo "lxdbr0 주소를 모른다"; exit 1; }
MIRROR="$(mktemp -d /var/tmp/release-mirror.XXXXXX)"
cp -r "$ASSETS/$TAG_A" "$ASSETS/$TAG_B" "$MIRROR/"
# 바뀐 묶음: tag-a 의 묶음 이름만 바꾸고 SHA256SUMS 는 바꾸기 전 파일로 만든 뒤, 묶음 끝에 한 바이트를 붙인다.
TAG_T="v0.0.0-tampered"; VER_A="${TAG_A#v}"
mkdir -p "$MIRROR/$TAG_T"
cp "$ASSETS/$TAG_A/clovirassist-$VER_A.tar.gz" "$MIRROR/$TAG_T/clovirassist-0.0.0-tampered.tar.gz"
( cd "$MIRROR/$TAG_T" && sha256sum clovirassist-0.0.0-tampered.tar.gz >SHA256SUMS && printf 'x' >>clovirassist-0.0.0-tampered.tar.gz )
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=$BRIDGE_IP" -addext "subjectAltName=IP:$BRIDGE_IP" \
  -keyout "$MIRROR/mirror.key" -out "$MIRROR/mirror.crt" >/dev/null 2>&1
( cd "$MIRROR" && exec openssl s_server -quiet -accept "$PORT" -cert mirror.crt -key mirror.key -WWW ) >/dev/null 2>&1 &
MIRROR_PID=$!
cleanup() { kill "$MIRROR_PID" 2>/dev/null; rm -rf "$MIRROR"; }
trap cleanup EXIT
sleep 1
BASE="https://$BRIDGE_IP:$PORT"
echo "미러: $BASE (태그 $TAG_A · $TAG_B · $TAG_T)"

# ── 컨테이너 ──────────────────────────────────────────────────────────────────
banner "새 Ubuntu 24.04 컨테이너 ($CT)"
lxc delete -f "$CT" </dev/null >/dev/null 2>&1 || true
lxc launch ubuntu:24.04 "$CT" </dev/null >/dev/null 2>&1 || { echo "컨테이너 생성 실패"; exit 1; }
for _ in $(seq 1 60); do
  CT_IP="$(lxc list "$CT" -c 4 --format csv </dev/null | tr -d ' ' | cut -d'(' -f1)"
  [ -n "$CT_IP" ] && break; sleep 2
done
[ -n "${CT_IP:-}" ] || { echo "컨테이너 IP 를 못 받았다"; exit 1; }
cx 'cloud-init status --wait >/dev/null 2>&1 || true; . /etc/os-release; echo "$PRETTY_NAME"'
lxc file push "$MIRROR/mirror.crt" "$CT/usr/local/share/ca-certificates/rehearsal-mirror.crt" </dev/null >/dev/null
cx 'update-ca-certificates >/dev/null 2>&1; echo ca-ok'
T0=$(date +%s)

banner "Release 페이지에서 install.sh 하나를 받는다"
# 사람이 하는 그대로: 스크립트와 목록을 받고, 목록의 install.sh 줄로 맞춰 본다(이진 모드 표시 * 는 떼고 본다).
cat >"$MIRROR/check-installsh.sh" <<'CHECK'
cd /root/dl && awk '$2 == "install.sh" || $2 == "*install.sh" { print $1 "  install.sh" }' SHA256SUMS | sha256sum -c -
CHECK
lxc file push "$MIRROR/check-installsh.sh" "$CT/root/check-installsh.sh" </dev/null >/dev/null
OUT="$(cx "mkdir -p /root/dl && cd /root/dl && curl -fsSLO $BASE/$TAG_A/install.sh && curl -fsSLO $BASE/$TAG_A/SHA256SUMS && bash /root/check-installsh.sh")"
echo "$OUT" | tail -2
expect_in "$OUT" "install.sh: OK" "받은 install.sh 가 Release 의 SHA256SUMS 와 맞는다"

ARGS="--dns-name $DNS_NAME --bind-ip $CT_IP --release-base $BASE"

banner "preflight — 받아서 확인만 하고 아무것도 바꾸지 않는다"
OUT="$(cx "cd /root/dl && bash install.sh preflight $ARGS")"
echo "$OUT" | tail -3
expect_in "$OUT" "STAGE_0_PREFLIGHT: OK" "Preflight 가 Release 를 받아 확인한다"
expect_in "$OUT" "체크섬을 확인했습니다" "Preflight 가 체크섬 확인을 말한다"
OUT="$(cx 'ls /opt/clovirassist 2>&1 | head -1')"
expect_in "$OUT" "No such file" "Preflight 뒤에 설치 자리가 없다"

banner "install — 태그를 주지 않는다(파일에 적힌 태그를 쓴다)"
OUT="$(cx "cd /root/dl && bash install.sh install $ARGS 2>&1")"
echo "$OUT" | grep -E '^STAGE_|INSTALL_|설정 코드' | mask
expect_in "$OUT" "INSTALL_OK" "Clean 설치가 끝난다"
expect_not "$OUT" ": FAIL" "실패한 Stage 가 없다"
CODE="$(grep -oE '설정 코드: [A-Z0-9-]+' <<<"$OUT" | head -1 | sed 's/설정 코드: //')"
[ -n "$CODE" ] && ok "첫 관리자 설정 코드가 콘솔에 나온다" || bad "첫 관리자 설정 코드가 콘솔에 없다"
# 여러 로그를 하나로 이어 센다(grep -c 에 파일이 여럿이면 줄마다 파일 이름이 붙어 합이 틀린다).
LEAK="$(cx "cat /var/log/clovirassist/install-*.log | grep -c -F '$CODE' || true")"
[ "$LEAK" = "0" ] && ok "설정 코드가 설치 로그에 없다" || bad "설정 코드가 설치 로그에 $LEAK 번 남았다"

banner "clovirassist 명령"
OUT="$(cx 'clovirassist version')"
expect_in "$OUT" "release       : $TAG_A" "version 이 Release 태그를 말한다"
OUT="$(cx 'clovirassist verify')"
expect_in "$OUT" "VERIFY_OK" "verify 가 통과한다"
expect_in "$OUT" "[OK ] 운영 명령 /usr/local/bin/clovirassist 이 있다" "verify 가 운영 명령을 본다"

banner "첫 관리자 만들기"
ADMIN_PW="Rehearsal-$(openssl rand -hex 6)-A1!"
CURL="curl -s --cacert /etc/clovirassist/tls/$DNS_NAME.crt --resolve $DNS_NAME:443:$CT_IP"
BODY="{\"code\":\"$CODE\",\"email\":\"admin@rehearsal.invalid\",\"name\":\"리허설 관리자\",\"password\":\"$ADMIN_PW\",\"password_confirm\":\"$ADMIN_PW\"}"
lxc exec "$CT" -- bash -c "cat >/root/fa.json" <<<"$BODY"
OUT="$(cx "$CURL -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' --data @/root/fa.json https://$DNS_NAME/setup/first-admin; rm -f /root/fa.json")"
[ "$OUT" = "201" ] && ok "설정 코드로 시스템 관리자를 만든다(201)" || bad "첫 관리자 만들기가 $OUT 이다"
OUT="$(cx "$CURL -o /dev/null -w '%{http_code}' https://$DNS_NAME/setup/first-admin")"
[ "$OUT" = "404" ] && ok "계정이 생기면 첫 관리자 화면이 닫힌다(404)" || bad "첫 관리자 화면이 $OUT 이다"
LOGIN="{\"email\":\"admin@rehearsal.invalid\",\"password\":\"$ADMIN_PW\"}"
lxc exec "$CT" -- bash -c "cat >/root/login.json" <<<"$LOGIN"
OUT="$(cx "$CURL -c /root/jar -H 'Content-Type: application/json' --data @/root/login.json https://$DNS_NAME/login; rm -f /root/login.json")"
CSRF="$(grep -oE '\"csrf_token\": *\"[^\"]+\"' <<<"$OUT" | sed -E 's/.*: *\"([^\"]+)\"/\1/')"
[ -n "$CSRF" ] && ok "만든 관리자로 로그인한다" || bad "로그인하지 못했다"
API="$CURL -b /root/jar -H 'X-CSRF-Token: $CSRF' -H 'Content-Type: application/json'"

banner "메일 연결 확인(컨테이너 안의 시험용 SMTP)"
cx 'DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-aiosmtpd tinyproxy >/dev/null 2>&1; echo apt-done' | tail -1
cx 'nohup python3 -m aiosmtpd -n -l 127.0.0.1:2525 >/root/smtp.log 2>&1 & sleep 1; echo smtp-up'
SMTP='{"value":{"enabled":true,"host":"127.0.0.1","port":2525,"security":"none","from_address":"portal@rehearsal.invalid","from_name":"ClovirAssist"}}'
OUT="$(cx "$API -X PUT -o /dev/null -w '%{http_code}' --data '$SMTP' https://$DNS_NAME/api/admin/settings/smtp")"
[ "$OUT" = "200" ] && ok "메일 설정을 저장한다" || bad "메일 설정 저장이 $OUT 이다"
JOB="$(cx "$API -X POST https://$DNS_NAME/api/admin/mail/verify" | grep -oE '\"job_id\": *\"[^\"]+\"' | sed -E 's/.*\"([^\"]+)\"$/\1/')"
RES=""
for _ in $(seq 1 45); do
  RES="$(cx "$API https://$DNS_NAME/api/admin/mail/verify/$JOB")"
  grep -qE '"pending": ?true' <<<"$RES" || break; sleep 2
done
expect_re "$RES" '"ok": ?true' "메일 연결 확인이 잡으로 돌아 성공한다"
OUT="$(cx "$API https://$DNS_NAME/api/admin/setup/checklist")"
expect_re "$OUT" '"key": ?"mail"' "초기 설정이 메일 항목을 보인다"

banner "바깥 프록시 뒤 AI 연결 확인(가짜 키 - 요청이 프록시를 지나는지 본다)"
cx 'systemctl restart tinyproxy; : >/var/log/tinyproxy/tinyproxy.log; echo proxy-up' | tail -1
OUT="$(cx "$API -X POST --data '{\"params\":{\"url\":\"http://127.0.0.1:8888\"}}' https://$DNS_NAME/api/admin/system/proxy.set")"
expect_re "$OUT" '"ok": ?true' "시스템 설정이 프록시 드롭인을 쓴다"
restart_units
OUT="$(cx "systemctl show clovirassist-worker -p Environment")"
expect_in "$OUT" "HTTPS_PROXY=http://127.0.0.1:8888" "배치 워커가 프록시 환경을 받는다"
OUT="$(cx "$API -X PUT -o /dev/null -w '%{http_code}' --data '{\"value\":\"sk-ant-rehearsal-not-a-real-key\"}' https://$DNS_NAME/api/admin/secrets/ai.anthropic.api_key")"
[ "$OUT" = "200" ] && ok "가짜 API 키를 비밀 슬롯에 넣는다(값은 되읽지 않는다)" || bad "비밀 슬롯 저장이 $OUT 이다"
OUT="$(cx "$API -X PUT -o /dev/null -w '%{http_code}' --data '{\"provider\":\"anthropic\",\"auth_method\":\"api_key\",\"model\":\"claude-haiku-4-5-20251001\",\"generation_enabled\":true}' https://$DNS_NAME/api/admin/ai/config")"
[ "$OUT" = "200" ] && ok "AI 설정(Anthropic, API 키)을 저장한다" || bad "AI 설정 저장이 $OUT 이다"
verify_ai() {
  local job res
  job="$(cx "$API -X POST https://$DNS_NAME/api/admin/ai/verify" | grep -oE '\"job_id\": *\"[^\"]+\"' | sed -E 's/.*\"([^\"]+)\"$/\1/')"
  for _ in $(seq 1 45); do
    res="$(cx "$API https://$DNS_NAME/api/admin/ai/verify/$job")"
    grep -qE '"pending": ?true' <<<"$res" || break; sleep 2
  done
  echo "$res"
}
RES="$(verify_ai)"
echo "$RES" | head -c 400; echo
N1="$(cx "grep -c 'CONNECT api.anthropic.com:443' /var/log/tinyproxy/tinyproxy.log")"
[ "${N1:-0}" -ge 1 ] && ok "AI 연결 확인이 프록시를 지났다(CONNECT ${N1}번)" || bad "프록시 로그에 AI 제공자 연결이 없다"
expect_re "$RES" '"ok": ?false' "가짜 키는 거절된다(연결 확인이 성공으로 뭉개지지 않는다)"
# 거절의 자리가 중요하다: 제공자가 키를 거절했으면 상태는 인증 · 구성 오류(error)다. 미설정이면 바깥에 나가지도 않은 것이다.
expect_re "$RES" '"state": ?"error"' "제공자가 키를 거절했다(요청이 실제로 바깥에 닿았다)"
OUT="$(cx "$API -X POST --data '{\"params\":{\"enabled\":false}}' https://$DNS_NAME/api/admin/system/proxy.set")"
expect_re "$OUT" '"ok": ?true' "프록시를 해제한다"
restart_units
RES="$(verify_ai)"
expect_re "$RES" '"state": ?"error"' "프록시 없이도 제공자에 닿아 같은 거절을 받는다"
N2="$(cx "grep -c 'CONNECT api.anthropic.com:443' /var/log/tinyproxy/tinyproxy.log")"
[ "${N2:-0}" = "${N1:-0}" ] && ok "프록시를 해제하면 직접 연결한다(프록시 로그가 늘지 않는다)" || bad "프록시를 해제했는데 프록시를 지났다"

banner "같은 설치를 다시 돌린다(idempotent)"
BEFORE="$(cx "grep -E '\"(version|release_tag|alembic_head|source_kind)\"' /etc/clovirassist/installed_manifest.json")"
OUT="$(cx "clovirassist install --dns-name $DNS_NAME --bind-ip $CT_IP 2>&1")"
expect_in "$OUT" "INSTALL_OK" "다시 돌려도 끝난다"
expect_not "$OUT" "설정 코드:" "계정이 있으면 설정 코드를 다시 만들지 않는다"
AFTER="$(cx "grep -E '\"(version|release_tag|alembic_head|source_kind)\"' /etc/clovirassist/installed_manifest.json")"
[ "$BEFORE" = "$AFTER" ] && ok "manifest 의 버전, 태그, 스키마, 소스 종류가 같다" || bad "다시 돌리니 manifest 가 바뀌었다: $BEFORE → $AFTER"

banner "바뀐 묶음으로 업그레이드 시도 — 멈춰야 한다"
OUT="$(cx "clovirassist upgrade --release $TAG_T --release-base $BASE 2>&1")"
echo "$OUT" | grep -E '^STAGE_0|체크섬' | head -3
expect_in "$OUT" "체크섬이 맞지 않습니다" "바뀐 묶음은 풀지 않고 멈춘다"
OUT="$(cx 'clovirassist version')"
expect_in "$OUT" "release       : $TAG_A" "멈춘 뒤에도 설치는 그대로다"

banner "다음 태그로 업그레이드"
OUT="$(cx "clovirassist upgrade --release $TAG_B --release-base $BASE 2>&1")"
echo "$OUT" | grep -E '^STAGE_|UPGRADE_' | tail -4
expect_in "$OUT" "UPGRADE_OK" "업그레이드가 끝난다"
OUT="$(cx 'clovirassist version')"
expect_in "$OUT" "release       : $TAG_B" "version 이 새 태그를 말한다"
OUT="$(cx "$CURL -o /dev/null -w '%{http_code}' -b /root/jar https://$DNS_NAME/api/me")"
[ "$OUT" = "200" ] && ok "업그레이드 뒤에도 로그인 세션과 계정이 남아 있다" || bad "업그레이드 뒤 /api/me 가 $OUT 이다"

banner "되돌리기"
OUT="$(cx "clovirassist rollback 2>&1")"
echo "$OUT" | tail -8
expect_in "$OUT" "ROLLBACK_OK" "되돌리기가 끝난다"
OUT="$(cx 'cat /opt/clovirassist/VERSION')"
expect_in "$OUT" "${TAG_A#v}" "되돌린 설치가 이전 버전이다"

banner "제거"
OUT="$(cx "clovirassist uninstall --purge --yes 2>&1")"
expect_in "$OUT" "UNINSTALL_OK" "제거가 끝난다"
OUT="$(cx 'ls /usr/local/bin/clovirassist 2>&1')"
expect_in "$OUT" "No such file" "운영 명령도 지워진다"

T1=$(date +%s)
# 실패했으면 KEEP_ON_FAIL=1 일 때 컨테이너를 남겨 둔다 - 그 자리의 로그가 원인을 말한다.
if [ "$FAILED" -ne 0 ] && [ "${KEEP_ON_FAIL:-0}" = 1 ]; then
  echo "컨테이너 $CT 를 남겨 둡니다(lxc exec $CT -- bash). 다 보면 lxc delete -f $CT"
else
  lxc delete -f "$CT" </dev/null >/dev/null 2>&1 || true
fi
echo
echo "═══ 요약 ($(( (T1 - T0) / 60 ))분) ═══"
printf '%s\n' "${SUMMARY[@]}"
if [ "$FAILED" -eq 0 ]; then echo "RELEASE_REHEARSAL_OK"; else echo "RELEASE_REHEARSAL_FAILED"; exit 1; fi
