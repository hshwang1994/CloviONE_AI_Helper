#!/usr/bin/env bash
# Read-only pre-check (spec §4). Emits a masked markdown report and a JSON
# inventory to /home/cloviradmin/, and exits:
#   0  = proceed
#   10 = proceed with warnings
#   20 = STOP (reasons printed as "STOP: <reason>" lines)
# Never prints secret values; env files are reported by PATH only.
set -uo pipefail
export LC_ALL=C.UTF-8

case "$(head -c 200 "$0" 2>/dev/null)" in
  *$'\r'*) echo "CRLF detected in script"; exit 64;; esac

REPORT=/home/cloviradmin/clovirone-web-precheck.md
INVENTORY=/home/cloviradmin/clovirone-system-inventory.json
# 설치처 고유값. 기본값을 두지 않는다(설치 스크립트와 같은 이유: 저장소에 한 고객사의
# 호스트명·IP 를 박아 두면 다른 곳에서 남의 주소를 점검하고 통과해 버린다).
# 이 스크립트는 읽기 전용 사전 점검이라 값이 없다고 멈추지는 않지만, **확인하지 않았다는
# 사실을 반드시 말한다** - 빈 값으로 조용히 통과시키면 "점검 통과"가 "DNS 를 확인했다"로
# 읽힌다(§불변 6: 0 과 "없음" 과 "못 잼" 은 서로 다른 사실이다).
DNS_NAME="${DNS_NAME:-}"
EXPECT_IP="${EXPECT_IP:-}"

STOP=0
WARN=0
declare -a STOP_REASONS=()
declare -a WARN_REASONS=()

stop()  { STOP=1; STOP_REASONS+=("$1"); echo "STOP: $1"; }
warn()  { WARN=1; WARN_REASONS+=("$1"); echo "WARN: $1"; }

have_sudo=0
if sudo -n true 2>/dev/null; then have_sudo=1; fi

mask() { sed -E 's/((pass(word)?|secret|token|api[_-]?key)[[:space:]]*[=:][[:space:]]*)[^[:space:]]+/\1***REDACTED***/Ig'; }

json_escape() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e ':a;N;$!ba;s/\n/\\n/g' -e 's/^/"/' -e 's/$/"/'; }

# ---- collectors ----------------------------------------------------------
OS_RELEASE="$(cat /etc/os-release 2>/dev/null)"
KERNEL="$(uname -a)"
HOSTNAME_INFO="$(hostnamectl 2>/dev/null)"
NPROC="$(nproc 2>/dev/null)"
IP_ADDR="$(ip -brief address 2>/dev/null)"
IP_ROUTE="$(ip route 2>/dev/null)"
DNS_RESOLVE="$(getent ahostsv4 "$DNS_NAME" 2>/dev/null)"
DF_H="$(df -h 2>/dev/null)"
FREE_H="$(free -h 2>/dev/null)"
PYTHON_VER="$(python3 --version 2>&1)"
MEM_AVAIL_KB="$(awk '/MemAvailable/ {print $2}' /proc/meminfo 2>/dev/null)"

if [ "$have_sudo" = "1" ]; then
  SS_LNTP="$(sudo -n ss -lntp 2>/dev/null)"
  NGINX_T="$(sudo -n nginx -T 2>&1)"
  UFW_STATUS="$(sudo -n ufw status verbose 2>/dev/null)"
  NFT_RULES="$(sudo -n nft list ruleset 2>/dev/null | head -50)"
else
  SS_LNTP="$(ss -lntp 2>/dev/null)"
  NGINX_T="SKIPPED_NEEDS_ROOT"
  UFW_STATUS="SKIPPED_NEEDS_ROOT"
  NFT_RULES="SKIPPED_NEEDS_ROOT"
fi

FAILED_UNITS="$(systemctl --failed --no-pager 2>/dev/null)"
UNIT_FILES="$(systemctl list-unit-files --type=service 2>/dev/null | grep -Ei 'clovir|nginx' || true)"

# Existing service metadata (path/user only — no env contents)
declare -a KNOWN_UNITS=(nginx clovirone-web-assistant clovirone-web-worker)
SERVICES_JSON=""
for unit in "${KNOWN_UNITS[@]}"; do
  props="$(systemctl show -p LoadState,ActiveState,SubState,User,ExecStart,EnvironmentFiles,Restart "$unit" 2>/dev/null)"
  load="$(printf '%s\n' "$props" | awk -F= '/^LoadState=/{print $2}')"
  [ "$load" = "not-found" ] && continue
  active="$(printf '%s\n' "$props" | awk -F= '/^ActiveState=/{print $2}')"
  suser="$(printf '%s\n' "$props" | awk -F= '/^User=/{print $2}')"
  execstart="$(printf '%s\n' "$props" | sed -n 's/^ExecStart=.*path=\([^ ;]*\).*/\1/p' | head -1)"
  envfiles="$(printf '%s\n' "$props" | awk -F= '/^EnvironmentFiles=/{print $2}')"
  restart="$(printf '%s\n' "$props" | awk -F= '/^Restart=/{print $2}')"
  SERVICES_JSON="${SERVICES_JSON}{\"unit\":\"$unit\",\"active\":\"$active\",\"user\":\"$suser\",\"exec\":\"$execstart\",\"env_file_path\":\"${envfiles%% *}\",\"restart\":\"$restart\"},"
  [ "$active" = "failed" ] && stop "existing service '$unit' is failed"
done
SERVICES_JSON="[${SERVICES_JSON%,}]"

# Ports of interest
declare -A PORT_OWNER=()
for p in 80 443 8080; do
  line="$(printf '%s\n' "$SS_LNTP" | grep -E "[:.]$p " | head -1)"
  PORT_OWNER[$p]="$line"
done

# TLS certs (public only)
CERT_INFO=""
if [ "$have_sudo" = "1" ]; then
  while IFS= read -r crt; do
    [ -z "$crt" ] && continue
    subj="$(sudo -n openssl x509 -noout -subject -enddate -ext subjectAltName -in "$crt" 2>/dev/null | tr '\n' ' ' | mask)"
    [ -n "$subj" ] && CERT_INFO="${CERT_INFO}- \`$crt\`: ${subj}\n"
  done < <(sudo -n find /etc/ssl /etc/nginx/ssl /etc/pki /etc/clovirone-web-assistant/tls -maxdepth 4 \( -name '*.crt' -o -name '*.pem' \) 2>/dev/null | head -20)
fi
[ -z "$CERT_INFO" ] && CERT_INFO="- (none found or needs root)\n"

# Internet reachability
PYPI_CODE="$(curl -sI --max-time 10 https://pypi.org 2>/dev/null | head -1)"
[ -n "$PYPI_CODE" ] && PYPI_OK=true || PYPI_OK=false
# 이 목록은 `scripts/install-clovirone-web-assistant.sh` 가 실제로 설치하는 것과 **같아야**
# 한다. 어긋나면 사전 점검이 초록인데 설치가 패키지에서 죽는다 — 사전 점검의 존재 이유가
# 정확히 그것을 미리 보는 것이다. `sqlite3` 자리를 `postgresql-client-16` 이 대신한다(D-187).
APT_SIM="$(apt-get -s install python3.12-venv nginx openssl postgresql-client-16 zip rsync 2>&1 | tail -5)"
echo "$APT_SIM" | grep -qiE 'newly installed|already the newest|0 upgraded' && APT_OK=true || APT_OK=false

# Existing clovirone-web install (re-run detection)
EXISTING_INSTALL=false
for d in /opt/clovirone-web-assistant /etc/clovirone-web-assistant /var/lib/clovirone-web-assistant; do
  [ -e "$d" ] && EXISTING_INSTALL=true
done
CLOVIRONE_WEB_USER="$(id clovirone-web 2>/dev/null && echo exists || echo absent)"

# ---- STOP condition evaluation (spec §3.2) -------------------------------
# DNS server-side
dns_ip="$(printf '%s\n' "$DNS_RESOLVE" | awk '{print $1}' | head -1)"
if [ -z "$DNS_NAME" ] || [ -z "$EXPECT_IP" ]; then
  # 못 잰 것을 통과로 세지 않는다. 어떻게 재는지도 같이 알려 준다.
  warn "DNS 미점검: DNS_NAME/EXPECT_IP 가 지정되지 않았다 (예: DNS_NAME=portal.example.internal EXPECT_IP=10.0.0.10 bash $0)"
elif [ -z "$dns_ip" ]; then
  warn "$DNS_NAME does not resolve on the server (may rely on /etc/hosts at deploy)"
elif [ "$dns_ip" != "$EXPECT_IP" ]; then
  stop "$DNS_NAME resolves to $dns_ip, expected $EXPECT_IP"
fi

# Port 8080 must be free
if [ -n "${PORT_OWNER[8080]}" ]; then
  stop "port 8080 already in use: ${PORT_OWNER[8080]}"
fi
# Ports 80/443: nginx = coexist OK; non-nginx = STOP
for p in 80 443; do
  owner="${PORT_OWNER[$p]}"
  if [ -n "$owner" ]; then
    if printf '%s' "$owner" | grep -qi 'nginx'; then
      warn "port $p held by nginx — will add a server block, coexisting"
    else
      stop "port $p held by non-nginx process: $owner"
    fi
  fi
done
# Existing vhost claiming our server_name
# DNS_NAME 이 비면 이 grep 은 server_name 이 있는 **모든** vhost 에 걸린다(빈 문자열은 어디에나
# 매치한다) - 못 잰 것을 STOP 으로 바꿔 버리므로 값이 있을 때만 본다. 위에서 이미 WARN 했다.
if [ -n "$DNS_NAME" ] && printf '%s' "$NGINX_T" | grep -qiE "server_name[[:space:]].*${DNS_NAME}"; then
  stop "an existing nginx server_name matches ${DNS_NAME}"
fi
# Disk: require >= 2GB free on / and /var
for mnt in / /var /opt; do
  avail_kb="$(df -Pk "$mnt" 2>/dev/null | awk 'NR==2{print $4}')"
  [ -z "$avail_kb" ] && continue
  if [ "$avail_kb" -lt 2097152 ]; then
    stop "less than 2GB free on $mnt (${avail_kb}KB)"
  fi
done
# Memory
if [ -n "$MEM_AVAIL_KB" ] && [ "$MEM_AVAIL_KB" -lt 409600 ]; then
  warn "low available memory: ${MEM_AVAIL_KB}KB"
fi
# Packages
if [ "$APT_OK" = false ] && [ "$PYPI_OK" = false ]; then
  warn "neither apt simulation nor PyPI reachable — offline install path may be needed"
fi

# ---- write JSON inventory ------------------------------------------------
{
  echo "{"
  echo "  \"generated_by\": \"00-precheck.sh\","
  echo "  \"hostname\": $(printf '%s' "$(hostname)" | json_escape),"
  echo "  \"kernel\": $(printf '%s' "$KERNEL" | json_escape),"
  echo "  \"python_version\": $(printf '%s' "$PYTHON_VER" | json_escape),"
  echo "  \"nproc\": \"${NPROC:-unknown}\","
  echo "  \"mem_available_kb\": \"${MEM_AVAIL_KB:-unknown}\","
  echo "  \"dns_resolves_to\": \"${dns_ip:-none}\","
  # "not-configured" 와 "none"(= 질의했는데 안 나왔다)을 다른 문자열로 남긴다.
  echo "  \"dns_expected\": \"${EXPECT_IP:-not-configured}\","
  echo "  \"pypi_reachable\": $PYPI_OK,"
  echo "  \"apt_ok\": $APT_OK,"
  echo "  \"existing_clovirone_web_install\": $EXISTING_INSTALL,"
  echo "  \"clovirone_web_user\": \"$(id -u clovirone-web 2>/dev/null && echo present || echo absent)\","
  echo "  \"services\": $SERVICES_JSON,"
  echo "  \"ports\": {"
  psep=""
  for p in 80 443 8080; do
    echo "    ${psep}\"$p\": $(printf '%s' "${PORT_OWNER[$p]}" | json_escape)"
    psep=","
  done
  echo "  },"
  echo "  \"stop\": $STOP,"
  echo "  \"warn\": $WARN"
  echo "}"
} > "$INVENTORY"

# ---- write masked markdown report ----------------------------------------
{
  echo "# ClovirONE Web Assistant — 사전조사 보고서"
  echo
  echo "생성: 00-precheck.sh (읽기 전용). 비밀번호/토큰/키 값은 포함되지 않습니다."
  echo
  echo "## 판정"
  if [ "$STOP" = "1" ]; then
    echo "- **STOP** — 아래 사유 해결 전 설치 금지"
    for r in "${STOP_REASONS[@]}"; do echo "  - $r"; done
  elif [ "$WARN" = "1" ]; then
    echo "- **진행 가능 (경고 있음)**"
    for r in "${WARN_REASONS[@]}"; do echo "  - $r"; done
  else
    echo "- **진행 가능**"
  fi
  echo
  echo "## 시스템"
  echo '```'
  echo "$HOSTNAME_INFO" | mask
  echo "$KERNEL"
  echo "python3: $PYTHON_VER"
  echo "nproc: $NPROC  mem_available_kb: ${MEM_AVAIL_KB:-?}"
  echo '```'
  echo "## 네트워크 / DNS"
  echo '```'
  echo "$IP_ADDR"
  echo "getent ${DNS_NAME:-(미지정)} -> ${dns_ip:-none} (expected ${EXPECT_IP:-(미지정)})"
  echo '```'
  echo "## 용량"
  echo '```'
  echo "$DF_H"
  echo
  echo "$FREE_H"
  echo '```'
  echo "## 리스닝 포트 (관심 대상)"
  echo '```'
  for p in 80 443 8080; do
    printf '%-5s %s\n' "$p" "${PORT_OWNER[$p]:-(free)}"
  done
  echo '```'
  echo "## 기존 서비스"
  echo '```'
  echo "$UNIT_FILES"
  echo
  echo "failed units:"
  echo "$FAILED_UNITS"
  echo '```'
  echo "## Nginx"
  echo '```'
  printf '%s\n' "$NGINX_T" | grep -iE 'server_name|listen|^\s*server\b|configuration file' | mask | head -60
  echo '```'
  echo "## TLS 인증서 (공개 정보)"
  echo -e "$CERT_INFO"
  echo "## 방화벽"
  echo '```'
  echo "$UFW_STATUS" | head -20
  echo '```'
  echo "## 인터넷 의존성"
  echo '```'
  echo "PyPI reachable: $PYPI_OK ($PYPI_CODE)"
  echo "apt install simulation ok: $APT_OK"
  echo '```'
  echo "## 기존 clovirone-web 설치 흔적"
  echo '```'
  echo "existing_install: $EXISTING_INSTALL"
  echo "clovirone-web user: $(id clovirone-web 2>/dev/null || echo absent)"
  echo '```'
} > "$REPORT"

chmod 600 "$REPORT" "$INVENTORY" 2>/dev/null || true

echo "REPORT: $REPORT"
echo "INVENTORY: $INVENTORY"
if [ "$STOP" = "1" ]; then
  echo "RESULT name=00-precheck.sh rc=20"
  exit 20
elif [ "$WARN" = "1" ]; then
  echo "RESULT name=00-precheck.sh rc=10"
  exit 10
fi
echo "RESULT name=00-precheck.sh rc=0"
exit 0
