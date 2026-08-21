#!/usr/bin/env bash
# S1 / P-03 — user-space PostgreSQL 16 + pgvector + pg_trgm on the test server.
# No sudo: official .deb packages are extracted into a relocatable prefix.
# Nothing outside $BASE and /tmp/s1deb is touched.
set -uo pipefail

BASE="$HOME/s1pg"
DEB="/tmp/s1deb"
ROOT="$BASE/root"
DATA="$BASE/data"
SOCK="$BASE/sock"
PORT=55432
PGBIN="$ROOT/usr/lib/postgresql/16/bin"

step() { echo "== $* =="; }

step "0 layout"
mkdir -p "$DEB" "$ROOT" "$SOCK" || exit 1
chmod 700 "$SOCK"
cd "$DEB" || exit 1

step "1 resolve dependency closure (not-installed only)"
WANT="postgresql-16 postgresql-16-pgvector postgresql-contrib postgresql-client-16"
CLOSURE=$(apt-cache depends --recurse --no-recommends --no-suggests \
            --no-conflicts --no-breaks --no-replaces --no-enhances $WANT 2>/dev/null \
          | grep -E '^[a-zA-Z0-9]' | sed 's/:.*//' | sort -u)
NEED=""
for p in $CLOSURE; do
  st=$(dpkg-query -W -f='${Status}' "$p" 2>/dev/null || true)
  case "$st" in
    *"install ok installed"*) ;;
    *) apt-cache show "$p" >/dev/null 2>&1 && NEED="$NEED $p" ;;
  esac
done
echo "need:$(echo $NEED | wc -w) packages"
echo "$NEED" | tr ' ' '\n' | grep -v '^$' > "$BASE/need.txt"

step "2 download"
# shellcheck disable=SC2086
apt-get download $NEED > "$BASE/download.log" 2>&1
rc=$?
echo "apt-get download rc=$rc  files=$(ls -1 *.deb 2>/dev/null | wc -l)"
[ "$(ls -1 *.deb 2>/dev/null | wc -l)" -gt 0 ] || { echo "FATAL no debs"; exit 1; }

step "3 extract"
for f in *.deb; do dpkg-deb -x "$f" "$ROOT" || echo "extract-fail $f"; done
echo "extracted; postgres bin: $(ls -1 "$PGBIN" 2>/dev/null | wc -l) files"

step "4 runtime env"
cat > "$BASE/env.sh" <<EOF
export PGHOME="$ROOT"
export PATH="$PGBIN:\$PATH"
export LD_LIBRARY_PATH="$ROOT/usr/lib/x86_64-linux-gnu:$ROOT/usr/lib/postgresql/16/lib:\${LD_LIBRARY_PATH:-}"
export PGDATA="$DATA"
export PGPORT=$PORT
export PGHOST="$SOCK"
export PGDATABASE=s1bench
EOF
# shellcheck disable=SC1090
. "$BASE/env.sh"

step "5 binary check"
"$PGBIN/postgres" --version || { echo "FATAL postgres --version"; ldd "$PGBIN/postgres" | grep "not found"; exit 1; }
ldd "$PGBIN/postgres" | grep "not found" && echo "WARN missing libs"

step "6 initdb"
if [ ! -f "$DATA/PG_VERSION" ]; then
  "$PGBIN/initdb" -D "$DATA" --encoding=UTF8 --locale=C.UTF-8 -U cloviradmin \
    > "$BASE/initdb.log" 2>&1 || { echo "FATAL initdb"; tail -20 "$BASE/initdb.log"; exit 1; }
fi
echo "initdb ok: $(cat "$DATA/PG_VERSION")"

step "7 tune + start"
cat > "$DATA/conf.d.s1" <<'EOF'
EOF
{
  echo "listen_addresses = ''"
  echo "port = $PORT"
  echo "unix_socket_directories = '$SOCK'"
  echo "shared_buffers = 2GB"
  echo "work_mem = 64MB"
  echo "maintenance_work_mem = 1GB"
  echo "effective_cache_size = 8GB"
  echo "max_parallel_workers_per_gather = 2"
  echo "logging_collector = off"
} >> "$DATA/postgresql.conf"

"$PGBIN/pg_ctl" -D "$DATA" -l "$BASE/server.log" -w -t 60 start \
  || { echo "FATAL pg_ctl start"; tail -30 "$BASE/server.log"; exit 1; }

step "8 extensions"
"$PGBIN/psql" -h "$SOCK" -p $PORT -d postgres -v ON_ERROR_STOP=1 <<'SQL'
SELECT version();
DROP DATABASE IF EXISTS s1bench;
CREATE DATABASE s1bench;
SQL
"$PGBIN/psql" -h "$SOCK" -p $PORT -d s1bench -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SELECT extname, extversion FROM pg_extension ORDER BY 1;
SQL
rc=$?
echo "PG_BOOTSTRAP_RC=$rc"
[ $rc -eq 0 ] && echo "PG_BOOTSTRAP_OK"
