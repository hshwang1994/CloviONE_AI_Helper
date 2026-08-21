#!/usr/bin/env bash
# Post-install validation (spec §35). Run as root (for full ss -lntp PIDs).
set -uo pipefail
export LC_ALL=C.UTF-8
# 설치처 고유값. 기본값을 두지 않는다 - 저장소에 한 고객사의 호스트명을 박아 두면 다른 곳에서
# 이 검증이 **남의 서버**를 찌르고 OK 를 낸다. 무엇을 검증했는지가 거짓이 된다.
DNS_NAME="${DNS_NAME:-}"
# BIND_IP 도 받는다. 설치 스크립트가 이미 둘 다 요구하므로 설치한 사람은 둘 다 안다.
#
# ⚠️ **이름만으로 자기 서버를 부르면 안 된다.** nginx 는 `__BIND_IP__:443` 한 곳에만 묶이는데,
# 서버 자신의 `/etc/hosts` 는 그 이름을 `127.0.1.1`(자기 호스트명 줄)로 푼다. 그래서 서버에서
# `curl https://$DNS_NAME/…` 은 nginx 가 아닌 곳을 찌르고 **연결조차 안 된다** — 실제로
# 이 서버에서 code=000 이 나왔다. `--resolve` 로 실제 바인딩 주소를 지정한다.
BIND_IP="${BIND_IP:-}"
if [ -z "$DNS_NAME" ] || [ -z "$BIND_IP" ]; then
  echo "DNS_NAME 과 BIND_IP 를 지정해야 합니다(설치처마다 다른 값이라 기본값이 없습니다)."
  echo "예: DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 bash $0"
  exit 2
fi
# 자체서명 설치처의 신뢰 기준점. 설치 스크립트가 만든 그 파일이다.
TLS_CERT="${TLS_CERT:-/etc/clovirone-web-assistant/tls/$DNS_NAME.crt}"
RESOLVE="--resolve $DNS_NAME:443:$BIND_IP --resolve $DNS_NAME:80:$BIND_IP"
FAIL=0
chk() { if eval "$2"; then echo "[OK ] $1"; else echo "[FAIL] $1"; FAIL=1; fi; }

echo "=== ClovirONE Web Assistant 검증 ==="
systemctl status clovirone-web-assistant --no-pager 2>/dev/null | head -3 || true
systemctl status clovirone-web-worker --no-pager 2>/dev/null | head -3 || true

chk "web service active" "systemctl is-active --quiet clovirone-web-assistant"
chk "worker service active" "systemctl is-active --quiet clovirone-web-worker"
chk "nginx active" "systemctl is-active --quiet nginx"
chk "existing n8n still active" "systemctl is-active --quiet n8n"

chk "app listening 127.0.0.1:8080" "ss -lntp 2>/dev/null | grep -q '127.0.0.1:8080'"
chk "nginx listening :443" "ss -lntp 2>/dev/null | grep -qE ':443'"

# ⚠️ 예전엔 이 둘이 `curl -k` 였다. `-k` 는 **아무것도 증명하지 않는다** — 인증서 이름이
# 어긋나 있어도, 남의 인증서여도 초록이다. 실제로 이 저장소는 제품 이름이 바뀐 뒤에도
# 옛 CN/SAN 인증서를 서브하고 있었는데 설치 검증은 계속 OK 였다. 이제 신뢰 기준점을 주고
# 진짜로 검증한다(자체서명 설치처에서는 그 인증서 자체가 기준점이다).
chk "healthz via nginx (TLS 검증)" "curl -fsS --cacert '$TLS_CERT' $RESOLVE https://$DNS_NAME/healthz >/dev/null"
chk "readyz via nginx (TLS 검증)" "curl -fsS --cacert '$TLS_CERT' $RESOLVE https://$DNS_NAME/readyz >/dev/null"
chk "ssl_verify_result=0" \
  "[ \"\$(curl -s -o /dev/null --cacert '$TLS_CERT' $RESOLVE -w '%{ssl_verify_result}' https://$DNS_NAME/healthz)\" = 0 ]"

# 80 -> 443 이 **요청된 이름을 보존**하는지. `return 301 https://\$host…` 가 그 성질인데,
# 여기서 이름이 바뀌면 로그인 리다이렉트가 다른 origin 으로 튀어 세션이 끊긴다.
chk "80 -> 443 이 이름을 보존한다" \
  "curl -sI $RESOLVE http://$DNS_NAME/ | tr -d '\r' | grep -qi '^location: https://$DNS_NAME/'"

chk "no failed units" "[ -z \"\$(systemctl --failed --no-pager --plain 2>/dev/null | grep clovir)\" ]"

echo "--- TLS ---"
CERT_TEXT="$(echo | openssl s_client -connect "$BIND_IP:443" -servername "$DNS_NAME" 2>/dev/null | \
  openssl x509 -noout -subject -issuer -enddate -ext subjectAltName 2>/dev/null)"
echo "${CERT_TEXT:-(TLS 확인 불가)}"
# 서브되는 인증서가 **이 이름의 것**인지. 이름이 어긋난 인증서는 위의 `--cacert` 검증에서도
# 걸리지만, 무엇이 틀렸는지는 여기서만 보인다.
chk "인증서 CN 이 $DNS_NAME" "grep -q 'subject=.*CN *= *$DNS_NAME' <<<\"\$CERT_TEXT\""
chk "인증서 SAN 에 $DNS_NAME" "grep -q 'DNS:$DNS_NAME' <<<\"\$CERT_TEXT\""

# 같은 이름을 두 server 블록이 들면 nginx 는 경고만 내고 **첫 번째가 조용히 이긴다** —
# 인증서를 고친 블록이 두 번째면 아무것도 안 바뀐 것처럼 보인다.
SRV_COUNT="$(nginx -T 2>/dev/null | grep -cE "^[[:space:]]*server_name[[:space:]].*\b$DNS_NAME\b")"
chk "server_name $DNS_NAME 을 든 블록이 :80·:443 둘뿐" "[ \"$SRV_COUNT\" = 2 ]"

echo "--- ports ---"
ss -lntp 2>/dev/null | grep -E ':(80|443|8080|5678|8787|8788|8789)\b' || true

if [ "$FAIL" -eq 0 ]; then echo "VALIDATE_OK"; else echo "VALIDATE_FAILED"; fi
exit $FAIL
