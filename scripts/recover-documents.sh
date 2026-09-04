#!/usr/bin/env bash
# 운영에서 문서를 정상화한다 — 계측 · Notion 복구 · Confluence 가져오기 · 분류 · 색인.
#
# ## 왜 스크립트인가
#
# 이 다섯 걸음은 **순서가 계약**이고, 되돌릴 수 없는 것이 섞여 있다. 손으로 옮기면
# 「dry-run 을 안 돌린 채 실행했다」나 「감사를 빼먹고 초록이라고 적었다」가 생긴다.
# 그리고 다시 돌릴 때 같은 명령이어야 결과를 비교할 수 있다.
#
# ## 자격증명 취급 (CLAUDE.md 불변규칙 3)
#
# `dist/ops/server.env`(gitignore)에서만 읽는다. sudo 비밀번호는 `sudo -S` 의 **stdin**
# 으로만 건넨다 — 명령행·로그·원격 `ps` 어디에도 안 남는다.
# `scripts/deploy-upgrade.sh` 와 **같은 규약**이다.
#
# ## 판정을 마지막 줄의 초록으로 하지 않는다
#
# `reimport-bodies` 의 `REIMPORT_OK` 는 「명령이 안 죽었다」이지 「내용이 돌아왔다」가
# 아니다. 그 판정은 `audit` 단계의 **`FIDELITY_OK`** 가 한다.
#
# ## 쓰는 법
#
#   bash scripts/recover-documents.sh measure          # 읽기만. 아무것도 안 쓴다
#   bash scripts/recover-documents.sh notion-dry
#   bash scripts/recover-documents.sh notion
#   bash scripts/recover-documents.sh audit
#   bash scripts/recover-documents.sh confluence-dry
#   bash scripts/recover-documents.sh confluence
#   bash scripts/recover-documents.sh classify-emit
#   bash scripts/recover-documents.sh classify-upload var/classify_manual.jsonl
#   bash scripts/recover-documents.sh classify-apply
#   bash scripts/recover-documents.sh reindex
set -uo pipefail
export LC_ALL=C.UTF-8

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CLOVIR_OPS_ENV:-dist/ops/server.env}"
[ -f "$ENV_FILE" ] || { echo "FAIL: $ENV_FILE 가 없다"; exit 2; }
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${SERVER:?SERVER 가 $ENV_FILE 에 없다}"
: "${SUDO_PW:?SUDO_PW 가 $ENV_FILE 에 없다}"

STEP="${1:-}"
[ -n "$STEP" ] || { echo "FAIL: 단계를 주세요 (measure|notion-dry|notion|audit|confluence-dry|confluence|classify-emit|classify-upload|classify-apply-dry|classify-apply|reindex|status)"; exit 2; }

APP_DIR="/opt/clovirassist"
# 🔴 데이터베이스 이름을 손으로 적지 않는다. 실측에서 `clovir` 로 적었다가 「그런
# 데이터베이스가 없다」를 만났다 — 개발 기본값(`clovir`)과 설치본 이름이 다르다.
# 설치가 실제로 쓰는 이름을 서버에서 읽고, 없으면 설치본 기본값으로 떨어진다.
DB_NAME="${CLOVIR_DB:-clovirassist}"
VENV="$APP_DIR/venv/bin/python"
CACHE="/var/lib/clovirassist/migration-cache"
OUT="/var/lib/clovirassist/recovery"

# Notion 데이터베이스 id 다섯. 🔴 `discover()` 는 제목으로 `/v1/search` 를 뒤지는데
# 오늘 그 검색이 문서·문서 유형·카테고리를 안 돌려준다 — override 가 없으면 회차가
# 「데이터베이스를 찾지 못했습니다」로 죽는다. 값은 실측이고 캐시의 databases.json 과 같다.
DBS=(
  "--database documents=262c5c5a-5684-8110-bdaf-de605ac15487"
  "--database doc_types=262c5c5a-5684-811b-86f3-fd88af5a2c40"
  "--database categories=262c5c5a-5684-812f-8bfb-dea96dcceb86"
  "--database tasks=262c5c5a-5684-81fa-9697-ee5691cb558d"
  "--database projects=262c5c5a-5684-8108-a949-c4503dd5f9a7"
)

# 원격에서 sudo 로 한 줄 돌린다. 비밀번호는 stdin 으로만 간다.
remote_sudo() {
  printf '%s\n' "$SUDO_PW" | ssh -o BatchMode=yes "$SERVER" "sudo -S -p '' $1" 2>&1 \
    | grep -v '^\[sudo\]'
}

# 제품 계정으로 앱 명령을 돌린다.
#
# 🔴 환경 파일을 **원격 셸 안에서** 읽는다. systemd 유닛은 `EnvironmentFile=` 로 그것을
# 넣어 주지만 손으로 돌리는 명령에는 아무도 안 넣어 준다 — 안 읽으면 `DATABASE_URL` 이
# 없어 「no password supplied」로 죽는다(실측). 그리고 이 방식이면 비밀번호가 명령행에
# 한 번도 안 나온다: 파일은 서버 안에서만 읽힌다(CLAUDE.md 불변규칙 3).
# 그 파일은 `root:clovirassist 0640` 이라 제품 계정이 읽을 수 있다.
APP_ENV="/etc/clovirassist/clovirassist.env"
app_cmd() {
  remote_sudo "-u clovirassist env HOME=/var/lib/clovirassist bash -lc 'set -a; . $APP_ENV; set +a; cd $APP_DIR && $1'"
}

case "$STEP" in

measure)
  echo "== 운영 실측 (읽기만) =="
  remote_sudo "-u postgres psql -d $DB_NAME -A -F'|' -t -c \"
    SELECT 'documents_total', count(*) FROM documents
    UNION ALL SELECT 'documents_archived', count(*) FROM documents WHERE archived
    UNION ALL SELECT 'source_'||source_type, count(*) FROM documents GROUP BY source_type
    UNION ALL SELECT 'with_legacy_page_id', count(*) FROM documents WHERE legacy_page_id IS NOT NULL
    UNION ALL SELECT 'migration_without_bridge', count(*) FROM documents
      WHERE source_type='MIGRATION' AND legacy_page_id IS NULL
    UNION ALL SELECT 'folder_in_use', count(*) FROM documents
      WHERE folder_id IS NOT NULL AND NOT archived
    UNION ALL SELECT 'space_'||owner_kind, count(*) FROM knowledge_spaces GROUP BY owner_kind
    UNION ALL SELECT 'placeholder_bodies', count(*) FROM documents d
      JOIN document_versions v ON v.id = d.current_version_id
      WHERE v.body_text LIKE '%원본에서 확인%'
    UNION ALL SELECT 'projects', count(*) FROM projects
    UNION ALL SELECT 'categories', count(*) FROM document_categories
    UNION ALL SELECT 'templates', count(*) FROM document_templates
    UNION ALL SELECT 'tags', count(*) FROM tags
    UNION ALL SELECT 'doc_comments', count(*) FROM document_comments
    UNION ALL SELECT 'doc_attachments', count(*) FROM document_attachments
    UNION ALL SELECT 'chunks', count(*) FROM document_chunks
    ORDER BY 1;\""
  ;;

notion-dry|notion)
  DRY=""
  [ "$STEP" = "notion-dry" ] && DRY="--dry-run"
  # 두 번째 인자부터 페이지 id 를 주면 **그 문서만** 고친다. 실측이 「110건 중 한 건만
  # 짧다」고 말할 때 110건을 통째로 다시 쓰지 않기 위한 자리다.
  #   bash scripts/recover-documents.sh notion 2a4c5c5a-5684-8092-9a03-d025a938fc4f
  PAGES=""
  shift || true
  for p in "$@"; do PAGES="$PAGES --page $p"; done
  echo "== Notion 문서 복구 $DRY ${PAGES:+(고른 페이지만)} =="
  # 🔴 --scope documents. 티켓 본문 약 1,120건에도 같은 자리표시자가 있지만 이번 요구는
  # 문서다 — 같은 회차에 함께 고치면 되돌릴 수 없는 변경의 범위가 열 배가 된다.
  app_cmd "$VENV -m app.cli.migrate_cli reimport-bodies \
    --cache $CACHE --scope documents --report $OUT/notion ${DBS[*]} $PAGES $DRY"
  ;;

audit)
  echo "== 복구가 실제로 무엇을 되살렸는가 =="
  # 판정은 이 단계가 한다. 위 명령의 REIMPORT_OK 는 「안 죽었다」일 뿐이다.
  app_cmd "$VENV scripts/audit_migration_fidelity.py \
    --database-url \"\$DATABASE_URL\" --json $OUT/fidelity.json"
  ;;

confluence-dry|confluence)
  DRY=""
  [ "$STEP" = "confluence-dry" ] && DRY="--dry-run"
  echo "== Confluence CMP · ClovirONE 가져오기 $DRY =="
  app_cmd "$VENV -m app.cli.migrate_cli import-confluence \
    --cache $CACHE --report $OUT/confluence $DRY"
  ;;

classify-emit)
  echo "== 프로젝트·분류·태그 제안 (아무것도 안 쓴다) =="
  app_cmd "$VENV -m app.cli.migrate_cli classify --emit $OUT/documents.jsonl"
  echo
  echo "🔴 다음은 **사람이 검토하는 단계다.** 위 파일을 받아서 읽고, 틀린 줄을 고친 뒤"
  echo "   classify-apply 를 돌린다. decision 은 matched|ambiguous|none|manual 이고,"
  echo "   손으로 고친 줄은 manual 로 적는다."
  ;;

classify-upload)
  # 검토를 끝낸 제안 파일을 서버로 올린다.
  #
  # 🔴 emit 이 만든 파일을 **서버에서 직접 고치지 않는다.** 검토는 여기(작업 PC)에서
  # 하고, 그 결과를 통째로 올린 다음 apply 가 그 파일만 읽는다. 줄마다 근거(`evidence`)가
  # 함께 적혀 있어서 「왜 이 문서가 저 프로젝트에 있나」에 나중에 답할 수 있고, 적용한
  # 그 파일이 서버의 $OUT 에 그대로 남는다. 파일에는 문서 id·제목·근거만 있고 비밀은 없다.
  LOCAL="${2:-var/classify_manual.jsonl}"
  [ -f "$LOCAL" ] || { echo "FAIL: $LOCAL 가 없다"; exit 2; }
  LINES=$(wc -l < "$LOCAL")
  echo "== 검토본 $LOCAL ($LINES 줄) 을 서버로 올린다 =="
  ssh -o BatchMode=yes "$SERVER" "cat > /tmp/classify-review.jsonl" < "$LOCAL" || exit 1
  remote_sudo "install -d -o clovirassist -g clovirassist -m 0750 $OUT"
  remote_sudo "install -o clovirassist -g clovirassist -m 0640 /tmp/classify-review.jsonl $OUT/documents.jsonl"
  remote_sudo "rm -f /tmp/classify-review.jsonl"
  echo "-- 서버가 받은 줄 수:"
  remote_sudo "wc -l $OUT/documents.jsonl"
  ;;

classify-apply-dry|classify-apply)
  DRY=""
  [ "$STEP" = "classify-apply-dry" ] && DRY="--dry-run"
  echo "== 검토한 제안을 적용한다 $DRY =="
  app_cmd "$VENV -m app.cli.migrate_cli classify --apply $OUT/documents.jsonl $DRY"
  ;;

status)
  # 색인 워커가 대기를 비웠는지 본다. `reindex` 는 큐에 넣기만 하므로, 「다 됐다」는
  # 이 단계가 pending 0 을 보여 줄 때 하는 말이다.
  app_cmd "$VENV -m app.cli.ai_cli status"
  ;;

reindex)
  echo "== AI 색인과 검색 색인을 다시 만든다 =="
  app_cmd "$VENV -m app.cli.ai_cli reindex"
  echo "-- index 워커가 대기를 비울 때까지 둔다. 상태:"
  app_cmd "$VENV -m app.cli.ai_cli status"
  ;;

*)
  echo "FAIL: 모르는 단계입니다: $STEP"; exit 2 ;;
esac
