"""notion_mapping_sync job handler — Notion 매핑을 한 번에 맞춘다 (spec §12, §22).

지금까지 매핑은 사용자 한 명씩 '검증' 버튼을 눌러야 했고, 그 버튼이 n8n을 **동기로** 불렀다.
그 워크플로는 Notion의 작업·프로젝트 DB를 통째로 읽어 9~13초가 걸린다(실측). 12명이면
브라우저를 2분 붙잡는다. 게다가 사람마다 같은 조회를 처음부터 다시 한다.

사용자 제안대로 작업 큐로 옮긴다: '동기화' 한 번 → 잡 하나 → 워커가 n8n을 한 번 부르고
그 결과로 **전원을 맞춘다**. 화면은 잡 상태를 폴링한다(채팅과 같은 방식).

실패는 조용히 넘기지 않는다. Notion을 못 읽었는데 '일치하는 사용자가 없다'로 답하면
사용자는 그 사람이 Notion에 없다고 믿는다 — 이 파일이 막으려는 것이 그 오해다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.http_client import is_timeout_error, is_transport_error
from app.workflows.provider_n8n import N8nWorkflowProvider
from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.notion_mapping.service import (
    SOURCE_WORKFLOW,
    STATUS_CONFLICT,
    STATUS_UNMAPPED,
    STATUS_VERIFIED,
    get_mapping_workflow,
    get_or_create_mapping,
)
from app.users.models import User

logger = logging.getLogger("app.handlers.notion_mapping_sync")

# n8n이 Notion 작업 DB 전체를 읽는다. 실측 9~13초라 넉넉히 준다 — 짧게 잡으면 정상 조회를
# 실패로 만들고, 큐가 재시도하며 같은 무거운 조회를 반복한다.
SYNC_TIMEOUT_SECONDS = 90.0


def _match_for(email: str, people: list[dict]) -> list[dict]:
    """이메일이 같은 사람. 대소문자는 워크플로가 이미 맞춰 보낸다."""
    target = (email or "").strip().lower()
    if not target:
        return []
    return [p for p in people if (p.get("notion_email") or "").strip().lower() == target]


def handle_notion_mapping_sync(db: Session, job: Job, ctx: WorkerContext) -> None:
    # payload는 항상 {}(sync_all이 유일한 enqueue 지점) — 읽어 쓰는 필드는 없지만,
    # payload_json이 손상된 잡을 여기서 PermanentJobError로 조기에 잡는다.
    parse_payload(job)
    workflow = get_mapping_workflow(db)
    if workflow is None or not workflow.enabled:
        # 구성 문제는 재시도해도 낫지 않는다. 큐가 같은 실패를 반복하게 두지 않는다.
        raise PermanentJobError(
            "Notion 매핑 Workflow가 구성/활성화되지 않았습니다. "
            "관리자 콘솔의 Workflow 레지스트리에서 'notion-user-mapping'을 확인하세요."
        )

    provider = N8nWorkflowProvider(ctx.outbound_client)
    # DBTX: 아웃바운드 호출 직전 커밋 — SYNC_TIMEOUT_SECONDS(90초)짜리 호출을 이 세션이
    # 위 get_mapping_workflow() 읽기 시점의 스냅샷을 쥔 채로 통과하면, 응답을 받은 뒤의
    # 쓰기가 "database is locked"로 거부될 수 있다(app/core/db.py의 "begin" 이벤트 주석,
    # app/jobs/handlers/chat_message.py의 실측 사고와 같은 근거).
    db.commit()
    try:
        result = provider.invoke(workflow, {"action": "list_users"}, timeout=SYNC_TIMEOUT_SECONDS)
    except Exception as exc:
        # 타임아웃·연결 실패는 일시적일 수 있으니 큐가 재시도한다. 그 외는 영구 실패다.
        if is_timeout_error(exc) or is_transport_error(exc):
            raise
        raise PermanentJobError(f"Notion 사용자 목록 조회 실패: {type(exc).__name__}") from exc

    if not isinstance(result, dict):
        raise PermanentJobError("Notion 매핑 Workflow가 예상과 다른 응답을 보냈습니다.")
    if result.get("error"):
        # 워크플로가 스스로 실패를 보고했다. 빈 목록을 '사람이 없다'로 읽으면 안 된다.
        raise PermanentJobError(f"Notion 사용자 목록 조회 실패: {str(result['error'])[:200]}")

    people = result.get("users")
    if not isinstance(people, list):
        raise PermanentJobError("Notion 매핑 Workflow 응답에 users 목록이 없습니다.")

    now: datetime = ctx.clock.now()
    # payload는 항상 {}다 — POST /api/admin/notion-mapping/sync(app/notion_mapping/router.py
    # sync_all)가 유일한 호출부이고 user_id를 실어 보내지 않는다. 예전엔 여기서 payload의
    # user_id로 한 명만 스코프하는 branch가 있었지만 어떤 API/UI도 그 값을 채워 보낸 적이
    # 없는 죽은 코드였다(round28 감사 E) — 항상 전체 사용자를 대상으로 한다.
    query = select(User).where(User.archived_at.is_(None)) if hasattr(User, "archived_at") else select(User)
    users = db.execute(query).scalars().all()

    summary = {"verified": 0, "unmapped": 0, "conflict": 0}
    # 이 잡을 발동시킨 관리자(자동 동기화 버튼을 누른 사람) — 행위자로 감사에 남긴다.
    # 없으면(예: 스케줄러가 나중에 이 핸들러를 직접 건다면) None으로 두어 '시스템'으로 보인다.
    actor_id = getattr(job, "user_id", None)
    for user in users:
        row = get_or_create_mapping(db, user.id)
        before_status = row.status
        matches = _match_for(user.email, people)
        row.last_verified_at = now
        row.source = SOURCE_WORKFLOW
        if len(matches) == 1 and str(matches[0].get("notion_user_id") or "").strip():
            row.status = STATUS_VERIFIED
            row.notion_user_id = str(matches[0]["notion_user_id"]).strip()
            row.notion_email = matches[0].get("notion_email")
            row.error_message = None
            row.candidates_json = None
            summary["verified"] += 1
        elif len(matches) > 1:
            # 같은 이메일이 둘 이상이면 우리가 고르지 않는다 — 관리자가 정한다.
            row.status = STATUS_CONFLICT
            row.notion_user_id = None
            row.notion_email = None
            row.error_message = f"{len(matches)}명이 일치하여 충돌합니다. 관리자 해결 필요."
            row.candidates_json = json.dumps(matches, ensure_ascii=False)
            summary["conflict"] += 1
        else:
            row.status = STATUS_UNMAPPED
            row.notion_user_id = None
            row.notion_email = None
            row.error_message = "Notion 작업 데이터에서 이 이메일을 찾지 못했습니다."
            row.candidates_json = None
            summary["unmapped"] += 1

        # 이 잡 핸들러는 지금까지 결과를 aggregate count로 logger.info()만 했다 — 개별 사용자의
        # 상태 변경(특히 신규 conflict, verified→unmapped 같은 되돌림)은 어디에도 남지 않았다.
        # registry.js는 이미 각 행에 '감사 로그에서 보기'(object_type=user_notion_mapping,
        # object_id=user_id) 딥링크를 두고 있는데, sync가 만든 변경은 그 링크가 가리키는
        # 자리에 아무것도 없었다 — 상태가 실제로 바뀐 사용자만 한 건씩 남긴다(안 바뀐 다수를
        # 매번 로그로 남기면 감사 로그가 sync 실행마다 부풀어 신호가 묻힌다).
        if row.status != before_status:
            record_audit(
                db, actor_id=actor_id, action="notion_mapping.sync",
                object_type="user_notion_mapping", object_id=user.id,
                before={"status": before_status}, after={"status": row.status},
            )

    # 결과를 잡에 따로 남기지 않는다. Job에는 result 칸이 없고(있는 것은 last_error뿐),
    # 채팅 잡도 결과를 자기 도메인 객체(메시지)에 쓴다. 매핑도 마찬가지로 **매핑 행 자체가
    # 결과**이고 목록 API(mapping_view)가 이미 status·notion_user_id·error_message를 돌려준다.
    # 잡이 끝나면 화면은 그 목록을 다시 불러 결과를 본다.
    db.flush()
    logger.info(
        "notion mapping sync: notion=%d users=%d verified=%d unmapped=%d conflict=%d",
        len(people), len(users), summary["verified"], summary["unmapped"], summary["conflict"],
    )
