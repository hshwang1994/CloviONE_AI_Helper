#!/usr/bin/env bash
# PostgreSQL 이 **접속을 받을 때까지** 기다린다 (INSTALLATION.md §6).
#
# 왜 필요한가: 유닛의 `After=postgresql.service` 는 «PG 유닛이 active 가 된 뒤» 만
# 보장한다. active 와 «소켓이 접속을 받는다» 는 다르다 — 재부팅 직후 PG 는 active 로
# 표시된 뒤에도 recovery·초기화로 몇 초를 더 쓴다. 그 창에 웹·워커가 뜨면 접속에
# 실패하고 `Restart=on-failure` 로 몇 번 죽었다 되살아난다. 결과적으로 복구되지만
# 그건 운이지 설계가 아니다. 여기서 기다리면 첫 시도에 뜬다.
#
# 실패해도 유닛을 막지 않는다(`ExecStartPre=-`). 이 스크립트의 일은 «흔한 몇 초» 를
# 없애는 것이지 PG 장애를 판정하는 것이 아니다 — 그것은 health probe 의 일이다.
set -uo pipefail

TIMEOUT="${PG_WAIT_TIMEOUT_SECONDS:-60}"
DSN="${DATABASE_URL:-}"

# `pg_isready` 자리. `PG_BIN_DIR` 는 web.env 가 들고 있다(비우면 PATH 의 낮은 버전을
# 집는다 — 백업이 조용히 실패했던 그 원인, S2).
ISREADY="pg_isready"
if [ -n "${PG_BIN_DIR:-}" ] && [ -x "${PG_BIN_DIR}/pg_isready" ]; then
  ISREADY="${PG_BIN_DIR}/pg_isready"
fi
command -v "$ISREADY" >/dev/null 2>&1 || [ -x "$ISREADY" ] || {
  echo "pg_isready 가 없어 PostgreSQL 준비를 기다리지 않는다(PG_BIN_DIR 를 확인하라)."
  exit 0
}

deadline=$(( $(date +%s) + TIMEOUT ))
while :; do
  if [ -n "$DSN" ]; then
    "$ISREADY" --quiet --dbname "$DSN" && exit 0
  else
    "$ISREADY" --quiet && exit 0
  fi
  [ "$(date +%s)" -ge "$deadline" ] && break
  sleep 1
done

echo "PostgreSQL 이 ${TIMEOUT}초 안에 접속을 받지 않았다. 그대로 기동을 시도한다."
exit 0
