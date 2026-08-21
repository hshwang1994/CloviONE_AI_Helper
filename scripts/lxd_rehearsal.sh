#!/usr/bin/env bash
# LXD Clean 설치 리허설 (S4 · INSTALLATION.md §7).
#
#   sudo bash scripts/lxd_rehearsal.sh <source.tar.gz> [container-name]
#
# 컨테이너를 새로 만들고, 그 안에서 `deploy/install.sh` 의 전 경로를 한 번씩 돌린다:
# Clean 설치 → verify → 재실행(idempotent) → 실패 주입 → rollback → upgrade →
# 컨테이너 재시작 복구 → uninstall → 재설치 → 옛 slug 이전 → purge.
#
# ── 이 리허설이 증명하는 것과 증명하지 않는 것 ──────────────────────────────
#
# **증명한다**: 설치가 Clean OS 에서 처음부터 끝까지 돈다 · 재실행이 무해하다 · 실패한
# Stage 가 어디이고 왜인지 표준 출력만으로 판별된다 · rollback 이 실제로 되돌린다 ·
# `systemctl enable` 이 실제로 걸려 있어 init 이 다시 돌면 유닛이 스스로 돌아온다.
#
# **증명하지 않는다**(R15 — 여기에 과장을 적지 않는다):
#   * 진짜 커널 재부팅. `lxc restart` 는 컨테이너의 init 을 다시 돌릴 뿐이다.
#     호스트 재부팅까지 포함한 판정은 이 스크립트 밖에서 따로 한다.
#   * NFS/CIFS 마운트. 비특권 컨테이너에서는 제한된다 — Storage 검증은 S8 의 실 VM 몫이다.
#   * 실 장비의 성능·TLS 클라이언트 신뢰 저장소.
#   * **git clone 그 자체.** 소스는 tarball 로 넣는다(제품 기준 GitLab 주소가 아직 없다, R16).
#     그래서 Stage 3 은 «git 아님» 으로 지나가고, clone 직후의 실행 비트는 여기서 확인되지
#     않는다 — 그 한 자리는 tests/unit/test_deploy_wiring.py 가 git 인덱스 모드로 지킨다.
set -uo pipefail
export LC_ALL=C.UTF-8

SRC_TGZ="${1:-}"
CT="${2:-s4-rehearsal}"
[ -f "$SRC_TGZ" ] || { echo "소스 tarball 이 필요합니다: sudo bash $0 <source.tar.gz> [container]"; exit 64; }
command -v lxc >/dev/null 2>&1 || { echo "lxc 가 없습니다. LXD 를 먼저 준비하십시오."; exit 64; }

# 리허설용 이름. **설치처 이름을 여기 박지 않는다** — 저장소에 한 곳의 호스트명을 두면
# 다른 데서 돌렸을 때 남의 이름으로 인증서를 만든다(scripts/check_tenant_defaults.py 가 막는다).
# .invalid 는 절대 안 풀리는 예약 도메인(RFC 2606)이고, 검증은 --resolve 로 하므로 무해하다.
DNS_NAME="${DNS_NAME:-clovirassist.rehearsal.invalid}"
STEP=0
FAILED=0
declare -a SUMMARY=()

banner() { STEP=$((STEP+1)); echo; echo "═══ [$STEP] $* ═══"; }
record() { SUMMARY+=("$1"); }
ok()   { echo "[OK ] $1"; record "OK   $1"; }
bad()  { echo "[FAIL] $1"; record "FAIL $1"; FAILED=1; }
# 컨테이너 안에서 명령을 돌린다. `</dev/null` 이 없으면 lxc 가 남은 스크립트를 stdin 으로
# 삼켜 YAML 로 파싱하려 든다 — 실제로 그렇게 한 번 죽었다.
cx()  { lxc exec "$CT" -- bash -lc "$1" </dev/null | tr -d '\r'; }
cxq() { lxc exec "$CT" -- bash -lc "$1" </dev/null >/dev/null 2>&1; }

expect_in() { # <출력> <기대 문자열> <이름>
  if grep -qF -- "$2" <<<"$1"; then ok "$3"; else bad "$3 — 기대한 «$2» 가 출력에 없다"; fi
}

# ─────────────────────────────────────────────────────────────────────────────
banner "컨테이너를 새로 만든다 ($CT)"
lxc delete -f "$CT" </dev/null >/dev/null 2>&1 || true
# 진행률 표시를 버린다 — 로그가 그것만으로 수백 줄이 된다.
lxc launch ubuntu:24.04 "$CT" </dev/null >/dev/null 2>&1 || { echo "컨테이너 생성 실패"; exit 1; }
for _ in $(seq 1 40); do
  CT_IP="$(lxc list "$CT" -c 4 --format csv </dev/null | tr -d ' ' | cut -d'(' -f1)"
  [ -n "$CT_IP" ] && break
  sleep 2
done
[ -n "${CT_IP:-}" ] || { echo "컨테이너 IP 를 못 받았다"; exit 1; }
echo "컨테이너 IP: $CT_IP"
cx 'cloud-init status --wait >/dev/null 2>&1 || true; head -1 /etc/os-release'

banner "소스를 넣는다 (/opt/src/clovirassist)"
# /opt 에 둔다 — 컨테이너 `/tmp` 는 tmpfs 라 재시작에 지워지고, 뒤 단계가 같은 tarball 을
# 다시 쓴다(재설치·이전 리허설). 실제로 그렇게 한 번 멈췄다.
lxc file push "$SRC_TGZ" "$CT/opt/src.tar.gz" </dev/null >/dev/null 2>&1
cx 'rm -rf /opt/src/clovirassist && mkdir -p /opt/src/clovirassist && tar xzf /opt/src.tar.gz -C /opt/src/clovirassist && ls /opt/src/clovirassist | head'
SRC=/opt/src/clovirassist
INSTALL="$SRC/deploy/install.sh"
ARGS="--source local --dns-name $DNS_NAME --bind-ip $CT_IP"

# ─────────────────────────────────────────────────────────────────────────────
banner "preflight — 아무것도 바꾸지 않는다"
OUT="$(cx "bash $INSTALL preflight $ARGS 2>&1")"
echo "$OUT" | tail -6
expect_in "$OUT" "STAGE_0_PREFLIGHT: OK" "Preflight 가 통과한다"
expect_in "$OUT" "PREFLIGHT_OK" "Preflight 가 끝났다고 말한다"
if cxq 'test -d /opt/clovirassist'; then bad "preflight 가 무언가를 만들었다"; else ok "preflight 는 아무것도 만들지 않았다"; fi

banner "Clean 설치"
OUT="$(cx "bash $INSTALL install $ARGS 2>&1")"
echo "$OUT" | grep -E '^(STAGE_|INSTALL_|VERIFY_|\[FAIL\])' || true
expect_in "$OUT" "INSTALL_OK" "Clean 설치가 끝났다"
for n in 0 1 2 3 4 5 6 7 8 9 10 13 14 15 16 17 18; do
  grep -qE "^STAGE_${n}_[A-Z]+: OK" <<<"$OUT" || { bad "STAGE_$n 이 OK 가 아니다"; break; }
done
grep -qE "^STAGE_18_VERIFY: OK" <<<"$OUT" && ok "Stage 0~18 이 전부 OK(11·12 는 SKIP)"
expect_in "$OUT" "STAGE_11_STORAGE: SKIP" "아직 없는 Storage Component 를 SKIP 이라고 말한다"
expect_in "$OUT" "STAGE_12_AI: SKIP" "아직 없는 AI Component 를 SKIP 이라고 말한다"

banner "설치 직후 상태 — 유닛 · 매니페스트"
cx 'systemctl is-active postgresql nginx clovirassist-privhelper clovirassist-worker clovirassist-scheduler clovirassist-web; echo "--- enabled ---"; systemctl is-enabled postgresql nginx clovirassist-privhelper clovirassist-worker clovirassist-worker-conversational clovirassist-scheduler clovirassist-web'
OUT="$(cx 'systemctl is-active clovirassist-web clovirassist-worker clovirassist-scheduler clovirassist-privhelper | sort -u')"
[ "$OUT" = "active" ] && ok "떠 있어야 하는 유닛 넷이 전부 active" || bad "active 가 아닌 유닛이 있다: $OUT"
OUT="$(cx 'systemctl is-active clovirassist-worker-conversational')"
[ "$OUT" = "inactive" ] && ok "대화형 레인은 설정이 꺼져 있어 inactive — 정상 대기 상태다(D-118)" \
  || bad "대화형 레인이 inactive 가 아니다: $OUT"
cx 'cat /etc/clovirassist/installed_manifest.json'

banner "verify · version"
OUT="$(cx "bash $INSTALL verify --dns-name $DNS_NAME --bind-ip $CT_IP 2>&1")"
echo "$OUT"
expect_in "$OUT" "VERIFY_OK" "verify 가 통과한다(TLS 검증 포함)"
cx "bash $INSTALL version 2>&1"

banner "재실행이 무해한가 (idempotent)"
BEFORE="$(cx 'cat /etc/clovirassist/clovirassist.env | sha256sum; runuser -u clovirassist -- psql -d clovirassist -tAc "select count(*) from pg_tables where schemaname = current_schema()"')"
OUT="$(cx "bash $INSTALL install $ARGS 2>&1")"
echo "$OUT" | grep -E '^(STAGE_8|STAGE_9|INSTALL_)' || true
expect_in "$OUT" "INSTALL_OK" "두 번째 설치도 끝난다"
expect_in "$OUT" "기존 설정을 보존하고" "설정을 새로 만들지 않고 보존한다"
AFTER="$(cx 'cat /etc/clovirassist/clovirassist.env | sha256sum; runuser -u clovirassist -- psql -d clovirassist -tAc "select count(*) from pg_tables where schemaname = current_schema()"')"
[ "$BEFORE" = "$AFTER" ] && ok "설정 해시와 데이터가 그대로다" || bad "재실행이 설정/데이터를 바꿨다"

banner "의도적 실패 주입 — 어느 Stage 에서 왜 멈췄나"
OUT="$(cx "bash $INSTALL upgrade --inject-failure 9 --dns-name $DNS_NAME --bind-ip $CT_IP 2>&1")"
echo "$OUT" | grep -E '^(STAGE_9|INSTALL_FAILED|스냅샷)' || true
expect_in "$OUT" "STAGE_9_MIGRATION: FAIL" "실패한 Stage 의 번호와 이름이 표준 출력에 있다"
expect_in "$OUT" "INSTALL_FAILED stage=9" "어디서 멈췄는지 한 줄로 말한다"
grep -qE "^STAGE_1[0-8]" <<<"$OUT" && bad "실패 뒤에도 다음 Stage 로 넘어갔다" || ok "실패 지점에서 멈췄다(다음 Stage 없음)"
SNAP="$(cx 'ls -1d /var/backups/clovirassist/*/ | sort | tail -1' | tr -d "\r")"
echo "스냅샷: $SNAP"
cx "ls -la $SNAP"

banner "rollback — 스냅샷으로 되돌린다"
OUT="$(cx "bash $INSTALL rollback --target ${SNAP%/} 2>&1")"
echo "$OUT"
expect_in "$OUT" "체크섬 확인" "손상된 백업을 그냥 믿지 않는다"
expect_in "$OUT" "ROLLBACK_OK" "복원 뒤 verify 까지 통과한다"

banner "upgrade (정상)"
OUT="$(cx "bash $INSTALL upgrade --dns-name $DNS_NAME --bind-ip $CT_IP 2>&1")"
echo "$OUT" | grep -E '^(STAGE_18|UPGRADE_|스냅샷)' || true
expect_in "$OUT" "UPGRADE_OK" "업그레이드가 끝난다"

banner "init 을 다시 돌리면 스스로 돌아오는가 (lxc restart)"
# ⚠️ 진짜 커널 재부팅이 아니다(R15). 이것이 증명하는 것은 «systemctl enable 이 실제로
# 걸려 있어 init 이 다시 돌 때 사람이 아무 명령도 안 쳐도 유닛이 올라온다» 까지다.
lxc restart "$CT" </dev/null
sleep 5
for _ in $(seq 1 60); do
  cxq 'systemctl is-system-running --wait >/dev/null 2>&1 || true; systemctl is-active clovirassist-web' && break
  sleep 2
done
cx 'uptime -p; systemctl is-active postgresql nginx clovirassist-privhelper clovirassist-worker clovirassist-scheduler clovirassist-web'
OUT="$(cx 'systemctl is-active postgresql nginx clovirassist-privhelper clovirassist-worker clovirassist-scheduler clovirassist-web | sort -u')"
[ "$OUT" = "active" ] && ok "수동 명령 0회로 전 유닛이 돌아왔다" || bad "돌아오지 않은 유닛이 있다: $OUT"
# 유닛이 active 인 것과 8080 을 듣는 것은 다르다(Type=simple). 기다린 뒤에 판정한다.
cx 'for i in $(seq 1 60); do curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 && break; sleep 1; done'
OUT="$(cx "bash $INSTALL verify --dns-name $DNS_NAME --bind-ip $CT_IP 2>&1")"
expect_in "$OUT" "VERIFY_OK" "재시작 뒤에도 verify 가 통과한다"
cx 'runuser -u clovirassist -- psql -d clovirassist -tAc "select count(*) from pg_tables where schemaname = current_schema()"'

banner "uninstall (데이터는 남긴다)"
OUT="$(cx "bash $INSTALL uninstall 2>&1")"
echo "$OUT" | tail -6
expect_in "$OUT" "UNINSTALL_OK purge=0" "유닛과 소스만 지웠다고 말한다"
if cxq 'ls /etc/systemd/system/clovirassist-*.service 2>/dev/null'; then bad "유닛 파일이 남았다"; else ok "유닛 파일이 전부 사라졌다"; fi
if cxq 'test -d /var/lib/clovirassist && test -f /etc/clovirassist/clovirassist.env'; then ok "설정과 데이터는 남았다"; else bad "purge 없이 데이터를 지웠다"; fi

banner "재설치 — 설치본 자리에서 바로 (INSTALLATION §1 의 3줄 경로 모양)"
cx 'mkdir -p /opt/clovirassist && tar xzf /opt/src.tar.gz -C /opt/clovirassist'
OUT="$(cx "bash /opt/clovirassist/deploy/install.sh install --dns-name $DNS_NAME --bind-ip $CT_IP 2>&1")"
echo "$OUT" | grep -E '^(STAGE_3|STAGE_18|INSTALL_)' || true
expect_in "$OUT" "INSTALL_OK" "설치본 자리에서 실행한 설치도 끝난다"
expect_in "$OUT" "소스가 이미 /opt/clovirassist 에 있습니다" "자기 자신을 덮어쓰지 않는다"
OUT="$(cx 'runuser -u clovirassist -- psql -d clovirassist -tAc "select count(*) from pg_tables where schemaname = current_schema()"' | tr -d ' \r')"
[ "${OUT:-0}" -gt 1 ] && ok "uninstall → 재설치 뒤에도 스키마가 그대로다(public 표 $OUT개)" || bad "데이터가 사라졌다"

banner "옛 slug 설치를 이전한다 (R13)"
cx "bash $INSTALL uninstall --purge --yes 2>&1 | tail -3"
# 옛 설치의 모양만 만든다 — 경로·유닛·시스템 계정. 안의 내용은 이전 대상 판별에만 쓰인다.
cx 'set -e
    useradd --system --shell /usr/sbin/nologin --no-create-home clovirone-web 2>/dev/null || true
    mkdir -p /opt/clovirone-web-assistant /etc/clovirone-web-assistant/tls /etc/clovirone-web-assistant/secrets \
             /var/lib/clovirone-web-assistant/uploads /var/backups/clovirone-web-assistant /var/log/clovirone-web-assistant
    printf "APP_ENV=production\nDATABASE_URL=postgresql://clovirassist@/clovirassist?host=/var/run/postgresql\nSESSION_SECRET=oldsecret\nCONFIG_DIR=/etc/clovirone-web-assistant\nDATA_DIR=/var/lib/clovirone-web-assistant\n" > /etc/clovirone-web-assistant/web.env
    echo "old-upload" > /var/lib/clovirone-web-assistant/uploads/marker.txt
    echo "old-secret" > /etc/clovirone-web-assistant/secrets/notion_docs_token
    printf "[Unit]\nDescription=old web\n[Service]\nExecStart=/bin/true\n[Install]\nWantedBy=multi-user.target\n" > /etc/systemd/system/clovirone-web-assistant.service
    systemctl daemon-reload; systemctl enable clovirone-web-assistant.service >/dev/null 2>&1 || true
    true'
# 소스는 /opt/src 의 원본을 쓴다 — 방금 purge 가 /opt/clovirassist 를 지웠다.
OUT="$(cx "bash $INSTALL install $ARGS 2>&1")"
echo "$OUT" | grep -E '^(STAGE_0|STAGE_2|INSTALL_)' || true
expect_in "$OUT" "옛 slug 설치(clovirone-web-assistant)를 감지했습니다" "Preflight 가 옛 설치를 알아본다"
expect_in "$OUT" "INSTALL_OK" "이전 뒤 설치가 끝난다"
if cxq 'test -f /var/lib/clovirassist/uploads/marker.txt && test -f /etc/clovirassist/secrets/notion_docs_token'; then
  ok "업로드와 비밀이 새 자리로 따라왔다"
else bad "이전이 데이터를 남겨 두고 갔다"; fi
if cxq 'test -e /opt/clovirone-web-assistant || test -e /etc/clovirone-web-assistant || ls /etc/systemd/system/clovirone-*.service 2>/dev/null | grep -q .'; then
  bad "옛 정체성이 디스크에 남았다"
else ok "옛 경로·유닛이 남지 않았다"; fi
if cxq 'id clovirone-web'; then bad "옛 시스템 계정이 남았다"; else ok "옛 시스템 계정이 사라졌다"; fi

banner "uninstall --purge — 전부 지운다"
OUT="$(cx "bash $INSTALL uninstall --purge --yes 2>&1")"
echo "$OUT" | tail -4
expect_in "$OUT" "UNINSTALL_OK purge=1" "전부 지웠다고 말한다"
if cxq 'test -e /etc/clovirassist || test -e /var/lib/clovirassist || id clovirassist'; then
  bad "purge 뒤에도 남은 것이 있다"
else ok "설정·데이터·계정이 전부 사라졌다"; fi

# ─────────────────────────────────────────────────────────────────────────────
echo
echo "════════════════════ 리허설 요약 ════════════════════"
printf '%s\n' "${SUMMARY[@]}"
echo "─────────────────────────────────────────────────────"
if [ "$FAILED" -eq 0 ]; then
  echo "LXD_REHEARSAL_OK  (${#SUMMARY[@]}항)"
else
  echo "LXD_REHEARSAL_FAILED"
fi
exit "$FAILED"
