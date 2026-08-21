#!/usr/bin/env bash
# Reboot 복구 검증 (INSTALLATION.md §7.1 · U14).
#
#   sudo bash scripts/reboot_check.sh prep   <source.tar.gz> [container]
#   sudo reboot
#   sudo bash scripts/reboot_check.sh verify [container]
#
# **왜 두 조각인가**: 이 검사가 증명하려는 것은 「사람이 아무 명령도 안 쳐도 돌아온다」이다.
# 한 스크립트가 재부팅을 걸고 그대로 이어서 확인하면 그 사이에 사람이 무엇을 했는지
# 구분할 수 없다. `prep` 이 상태를 적어 두고 끝나고, 재부팅 뒤 `verify` 가 **그 적어 둔
# 것과 지금**을 비교한다. 그 사이에 이 스크립트는 아무것도 하지 않는다.
#
# ── `lxc restart` 와 무엇이 다른가 (R15) ──────────────────────────────────────
# `scripts/lxd_rehearsal.sh` 의 재시작 단계는 컨테이너의 init 을 다시 돌릴 뿐이다.
# 여기서는 **호스트 커널을 재부팅**한다: 부트로더 → 커널 → systemd → LXD → 컨테이너
# autostart → 제품 유닛. 그 사슬 전체가 사람 손 없이 이어지는지를 본다.
#
# 컨테이너 안에서 도는 것은 그대로 한계다 — NFS/CIFS 마운트와 실 장비 성능은 여전히
# 이 검사의 범위 밖이고 S8·S22 의 몫이다. 여기에 과장을 적지 않는다.
set -uo pipefail
export LC_ALL=C.UTF-8

MODE="${1:-}"
STATE_FILE=/var/lib/clovirassist-reboot-check.json
# 리허설용 이름. **설치처 이름을 여기 박지 않는다** — 저장소에 한 곳의 호스트명을 두면
# 다른 데서 돌렸을 때 남의 이름으로 인증서를 만든다(scripts/check_tenant_defaults.py 가 막는다).
# .invalid 는 절대 안 풀리는 예약 도메인(RFC 2606)이고, 검증은 --resolve 로 하므로 무해하다.
DNS_NAME="${DNS_NAME:-clovirassist.rehearsal.invalid}"
UNITS="postgresql nginx clovirassist-privhelper clovirassist-worker clovirassist-scheduler clovirassist-web"

cx() { lxc exec "$CT" -- bash -lc "$1" </dev/null | tr -d '\r'; }

case "$MODE" in
  prep)
    SRC_TGZ="${2:-}"; CT="${3:-s4-reboot}"
    [ -f "$SRC_TGZ" ] || { echo "소스 tarball 이 필요합니다"; exit 64; }
    echo "═══ 컨테이너 준비 ($CT) ═══"
    lxc delete -f "$CT" </dev/null >/dev/null 2>&1 || true
    lxc launch ubuntu:24.04 "$CT" </dev/null >/dev/null 2>&1 || { echo "컨테이너 생성 실패"; exit 1; }
    for _ in $(seq 1 40); do
      CT_IP="$(lxc list "$CT" -c 4 --format csv </dev/null | tr -d ' ' | cut -d'(' -f1)"
      [ -n "$CT_IP" ] && break
      sleep 2
    done
    [ -n "${CT_IP:-}" ] || { echo "컨테이너 IP 를 못 받았다"; exit 1; }
    cx 'cloud-init status --wait >/dev/null 2>&1 || true'
    lxc file push "$SRC_TGZ" "$CT/opt/src.tar.gz" </dev/null >/dev/null 2>&1
    cx 'rm -rf /opt/src/clovirassist && mkdir -p /opt/src/clovirassist && tar xzf /opt/src.tar.gz -C /opt/src/clovirassist'

    echo "═══ 설치 ═══"
    cx "bash /opt/src/clovirassist/deploy/install.sh install --source local --dns-name $DNS_NAME --bind-ip $CT_IP 2>&1 | tail -6"

    # 호스트가 다시 뜰 때 컨테이너도 스스로 뜬다. 이것을 켜 두지 않으면 재부팅 뒤 사람이
    # `lxc start` 를 쳐야 하고, 그러면 「수동 명령 0회」가 성립하지 않는다.
    lxc config set "$CT" boot.autostart true </dev/null
    systemctl enable snap.lxd.daemon >/dev/null 2>&1 || true

    # 재부팅 전 상태를 적어 둔다. `verify` 는 이 파일과 지금을 비교한다.
    local_tables="$(cx 'runuser -u clovirassist -- psql -d clovirassist -tAc "select count(*) from pg_tables where schemaname = current_schema()"' | tr -d ' ')"
    {
      printf '{\n'
      printf '  "container": "%s",\n' "$CT"
      printf '  "container_ip": "%s",\n' "$CT_IP"
      printf '  "dns_name": "%s",\n' "$DNS_NAME"
      printf '  "tables_before": "%s",\n' "$local_tables"
      printf '  "boot_id_before": "%s",\n' "$(cat /proc/sys/kernel/random/boot_id)"
      printf '  "prepared_at": "%s"\n' "$(date -Is)"
      printf '}\n'
    } >"$STATE_FILE"
    chmod 0644 "$STATE_FILE"
    echo "═══ 준비 완료 ═══"
    cat "$STATE_FILE"
    echo
    echo "REBOOT_PREP_OK — 이제 'sudo reboot' 한 뒤 'sudo bash $0 verify' 를 실행하십시오."
    ;;

  verify)
    CT="${2:-}"
    [ -f "$STATE_FILE" ] || { echo "준비 기록이 없습니다($STATE_FILE). prep 을 먼저 실행하십시오."; exit 64; }
    _get() { sed -n "s/^[[:space:]]*\"$1\":[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$STATE_FILE" | tail -1; }
    [ -n "$CT" ] || CT="$(_get container)"
    CT_IP="$(_get container_ip)"
    DNS_NAME="$(_get dns_name)"
    BEFORE_TABLES="$(_get tables_before)"
    BOOT_BEFORE="$(_get boot_id_before)"
    BOOT_NOW="$(cat /proc/sys/kernel/random/boot_id)"

    FAIL=0
    chk() { if eval "$2" >/dev/null 2>&1; then echo "[OK ] $1"; else echo "[FAIL] $1"; FAIL=1; fi; }

    echo "═══ 재부팅 복구 검증 ($CT) ═══"
    echo "  호스트 가동: $(uptime -p)"
    # 🔴 이것이 이 검사의 첫 단추다. boot_id 가 그대로면 **재부팅이 일어나지 않았고**,
    # 그 상태에서 아래 초록은 「원래 떠 있었다」는 뜻일 뿐이다.
    chk "호스트가 실제로 재부팅됐다(boot_id 가 바뀌었다)" "[ '$BOOT_BEFORE' != '$BOOT_NOW' ]"

    # 컨테이너가 스스로 떴는가. 여기서 `lxc start` 를 치면 검사가 뜻을 잃는다.
    for _ in $(seq 1 60); do
      [ "$(lxc list "$CT" -c s --format csv </dev/null | tr -d ' ')" = "RUNNING" ] && break
      sleep 5
    done
    chk "컨테이너가 수동 명령 없이 RUNNING" "[ \"\$(lxc list $CT -c s --format csv </dev/null | tr -d ' ')\" = RUNNING ]"

    for _ in $(seq 1 60); do
      cx 'systemctl is-active --quiet clovirassist-web' && break
      sleep 5
    done
    echo "  컨테이너 가동: $(cx 'uptime -p')"
    for u in $UNITS; do
      chk "$u active" "[ \"\$(cx \"systemctl is-active $u\")\" = active ]"
    done
    chk "실패한 유닛 0" "[ -z \"\$(cx 'systemctl --failed --plain --no-legend' | grep clovirassist)\" ]"

    # 헬스는 기다렸다가 본다 — 유닛 active 와 포트를 듣는 것은 다르다(Type=simple).
    cx 'for i in $(seq 1 60); do curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 && break; sleep 1; done'
    chk "/healthz 200" "cx 'curl -fsS http://127.0.0.1:8080/healthz'"
    chk "/readyz 200 (DB 까지 붙었다)" "cx 'curl -fsS http://127.0.0.1:8080/readyz'"

    AFTER_TABLES="$(cx 'runuser -u clovirassist -- psql -d clovirassist -tAc "select count(*) from pg_tables where schemaname = current_schema()"' | tr -d ' ')"
    chk "재부팅 전 데이터가 그대로다(표 $BEFORE_TABLES → $AFTER_TABLES)" "[ '$BEFORE_TABLES' = '$AFTER_TABLES' ] && [ '${AFTER_TABLES:-0}' -gt 1 ]"

    echo "  --- 제품 verify (TLS 검증 포함) ---"
    VOUT="$(cx "bash /opt/src/clovirassist/deploy/install.sh verify --dns-name $DNS_NAME --bind-ip $CT_IP 2>&1")"
    echo "$VOUT" | sed 's/^/  /'
    chk "install.sh verify 가 통과한다" "grep -q VERIFY_OK <<<\"\$VOUT\""

    echo
    if [ "$FAIL" -eq 0 ]; then echo "REBOOT_RECOVERY_OK"; else echo "REBOOT_RECOVERY_FAILED"; fi
    exit "$FAIL"
    ;;

  *)
    sed -n '2,20p' "$0"
    exit 64
    ;;
esac
