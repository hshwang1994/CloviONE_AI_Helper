#!/usr/bin/env bash
# Post-install validation (spec §35). Run as root (for full ss -lntp PIDs).
set -uo pipefail
export LC_ALL=C.UTF-8
DNS_NAME=clovirone-ai.gooddi.lab
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

chk "healthz via nginx" "curl -kfsS https://$DNS_NAME/healthz >/dev/null"
chk "readyz via nginx" "curl -kfsS https://$DNS_NAME/readyz >/dev/null"

chk "no failed units" "[ -z \"\$(systemctl --failed --no-pager --plain 2>/dev/null | grep clovir)\" ]"

echo "--- TLS ---"
echo | openssl s_client -connect ${DNS_NAME}:443 -servername $DNS_NAME 2>/dev/null | \
  openssl x509 -noout -subject -enddate 2>/dev/null || echo "(TLS 확인 불가)"

echo "--- ports ---"
ss -lntp 2>/dev/null | grep -E ':(80|443|8080|5678|8787|8788|8789)\b' || true

if [ "$FAIL" -eq 0 ]; then echo "VALIDATE_OK"; else echo "VALIDATE_FAILED"; fi
exit $FAIL
