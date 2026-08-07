"""내 활동 피드 — '내가 한 일'과 '나에게 일어난 일'을 한 줄기로 합친다.

## 왜 새 표를 만들지 않는가

두 사건은 이미 각각 기록되고 있다: 내가 한 일은 `audit_log`(actor = 나), 나에게 일어난
일은 `notifications`(user_id = 나). 세 번째 표를 만들면 같은 사건이 두 곳에 적히고,
한쪽만 기록하는 코드 경로가 생기는 순간 피드가 조용히 진실을 잃는다. 여기서는 **읽어서
합치기만** 한다 — 쓰기가 0이라 어긋날 여지가 없다.

## 감사 로그를 사용자에게 보여도 되는가

여기서 읽는 것은 `actor_id == 나` 인 행뿐이다. 즉 **내가 한 일**만 나온다. before/after
JSON 은 싣지 않는다 — 감사 화면(관리자용)이 다루는 값이고, 개인 피드에는 '무엇을 했는가'
한 줄이면 충분하다. 마스킹된 값이라도 굳이 개인 화면에 다시 펼칠 이유가 없다.

## 두 어휘를 한 표로 합치지 않는 이유

알림의 `related_object_type`(`chat_room`, `chat_mention`)과 감사의 `object_type`
(`notion_task`, `notion_document`, `board_post`…)은 **서로 다른 두 작성자가 만든 다른
어휘**다. 딥링크는 알림 쪽 표(`app/notifications/destinations.py`)를 **먼저** 물어보고,
거기 없는 감사 전용 유형만 아래 표가 답한다. 그래서 알림 목적지를 바꿀 곳은 여전히 한
곳이고, 이 파일은 감사 어휘에 대해서만 책임진다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.notifications.destinations import destination_for
from app.notifications.models import Notification

KIND_DID = "did"          # 내가 한 일 (audit_log)
KIND_HAPPENED = "happened"  # 나에게 일어난 일 (notifications)

# 감사 `object_type` → 화면 경로. 알림 표에 없는 것만 여기 둔다(모듈 docstring 참조).
# 목적지에 `{id}` 가 있는데 object_id 가 비면 링크를 만들지 않는다 — 목록만 열리는
# 링크는 사용자를 원점으로 돌려보낼 뿐이다.
AUDIT_DESTINATIONS: dict[str, str] = {
    "notion_task": "/tickets/{id}",
    "notion_document": "/team-docs/{id}",
    "board_post": "/board/{id}",
    "chat_room": "/chat-rooms/{id}",
}

# 감사 object_type → 한국어 명사. 화면에 'notion_task' 를 그대로 보이면 사용자는 자기가
# 무엇을 했는지 알 수 없다.
#
# **여기 빠진 유형이 있으면 문장이 "만듦" 처럼 목적어 없이 나온다** — 실제로 캡처에서 그렇게
# 보였다(`department.create` 가 표에 없어서). 그래서 tests/unit/test_activity_labels.py 가
# 코드가 실제로 쓰는 object_type 을 훑어 이 표에 다 있는지 확인한다.
OBJECT_LABELS: dict[str, str] = {
    "notion_task": "티켓",
    "notion_document": "문서",
    "document_comment": "문서 댓글",
    "document_sync": "문서 동기화",
    # 강제 재동기화/재색인 트리거(C7). 운영자가 지금 당장 다시 동기화/색인하라고 누른 경로다.
    "ticket_sync": "티켓 동기화",
    "search_index": "검색 색인",
    "document_generation": "문서 생성",
    "board_post": "게시글",
    "board_comment": "댓글",
    "board_attachment": "첨부",
    "chat_room": "채팅방",
    "ticket_comment": "티켓 댓글",
    "ticket_attachment": "티켓 첨부",
    "organization": "조직",
    "project": "프로젝트",
    "project_milestone": "마일스톤",
    "user": "계정",
    "user_notion_mapping": "Notion 연결",
    "approval": "승인",
    "backup": "백업",
    "integration": "외부 연동",
    "job": "작업",
    # 메일 발송(9-9 P4). 관리 콘솔의 시험 발송이 이 이름으로 감사에 남는다.
    "mail_delivery": "메일 발송",
    "runner": "러너",
    "schedule": "실행 일정",
    "schedule_run": "실행 이력",
    "template": "템플릿",
    "offboarding_run": "오프보딩",
    "session": "세션",
    # 아래는 라우터가 변수로 넘기는 값들이다(문자열 리터럴 grep 만으로는 안 보인다):
    #   app/org/router.py    audit_type="department" / "job_title"
    #   app/prompts/router.py object_type=kind → "prompt" | "policy"
    #   app/settings/service.py OBJECT_TYPE = "app_setting"
    #   app/workflows/service.py OBJECT_TYPE = "workflow"
    "department": "부서",
    "job_title": "직책",
    "prompt": "프롬프트",
    "policy": "정책",
    "app_setting": "설정",
    "workflow": "워크플로",
    #   app/sysops/router.py OBJECT_TYPE = "system_setting" (타임존·DNS·인증서 등 서버 설정)
    "system_setting": "시스템 설정",
    # 관리자 백로그 잔여(0033, PLAN Phase 6).
    "announcement": "공지",
    "ai_quota": "AI 쿼터",
    "approval_delegation": "승인 위임",
    "feature_flag": "기능 플래그",
    "restore_rehearsal": "복구 리허설",
    # Notion 관리(9-4)와 LLM 관리(9-5). 토큰 교체, 연결 테스트, 데이터베이스 생성이
    # 이 이름으로 감사에 남는다.
    "notion_token": "Notion 토큰",
    "notion_database": "Notion 데이터베이스",
    "llm_config": "AI 설정",
}

# 액션 문자열의 **마지막 조각** → 한국어 동사. 'ticket.body.update' 처럼 조각이 셋이어도
# 마지막이 동사라는 규약을 지켜 온 덕에 표 하나로 전부 읽을 수 있다.
VERB_LABELS: dict[str, str] = {
    "create": "만듦",
    "update": "고침",
    "delete": "지움",
    "trash": "휴지통으로 보냄",
    "claim": "가져감",
    "pin": "고정",
    "upload": "올림",
    "sync": "동기화",
    "publish": "발행",
    "enable": "켬",
    "disable": "끔",
    "login": "로그인",
    "logout": "로그아웃",
    "approve": "승인",
    "cancel": "취소",
    "retry": "재시도",
    "rollback": "되돌림",
    "clone": "복제",
    "verify": "확인",
    "run": "실행",
    "undo": "되돌림",
    # Notion / AI 연결 테스트(9-4, 9-5). 'notion.connection.test' 처럼 마지막이 동사다.
    "test": "연결 테스트",
}

# 위 규칙(명사 + 동사)으로 자연스럽게 읽히지 않는 액션은 통째로 문장을 준다.
ACTION_SENTENCES: dict[str, str] = {
    "user.login": "로그인했습니다",
    "user.logout": "로그아웃했습니다",
    "user.login_failed": "로그인에 실패했습니다",
    "user.password_change_self": "비밀번호를 변경했습니다",
    "user.password_change_failed": "비밀번호 변경에 실패했습니다",
    "profile.avatar.update": "프로필 사진을 바꿨습니다",
    "profile.avatar.delete": "프로필 사진을 지웠습니다",
    "profile.preferences.update": "알림, 방해금지 설정을 바꿨습니다",
    "profile.sessions.revoke_others": "내 다른 기기의 로그인을 모두 해제했습니다",
    "profile.sessions.revoke": "다른 기기의 로그인을 해제했습니다",
    "team_chat.create_group": "채팅방을 만들었습니다",
    "team_chat.disband": "채팅방을 파했습니다",
    "team_chat.rename": "채팅방 이름을 바꿨습니다",
    "team_chat.add_members": "채팅방에 사람을 초대했습니다",
    "team_chat.remove_member": "채팅방에서 사람을 내보냈습니다",
    "team_chat.transfer_owner": "채팅방 방장을 넘겼습니다",
}


def object_particle(word: str) -> str:
    """받침 유무에 따른 한국어 목적격 조사(을/를).

    "티켓을(를) 고침" 처럼 두 조사를 나란히 쓰면 기계가 쓴 문장처럼 읽힌다. 완성형 한글로
    끝나는 이름만 정확히 판정하고, 그 밖(영문·숫자로 끝나는 이름)은 '를' 로 둔다.
    (app/auth/router.py 의 `_subject_particle` 과 같은 계산 — 그쪽은 주격 이/가다.)
    """
    word = (word or "").strip()
    if not word:
        return "를"
    code = ord(word[-1])
    if 0xAC00 <= code <= 0xD7A3:
        # 완성형 한글 = (초성*21 + 중성)*28 + 종성 + 0xAC00. 종성이 0이면 받침 없음.
        return "를" if (code - 0xAC00) % 28 == 0 else "을"
    return "를"


def describe_action(action: str, object_type: str | None) -> str:
    """감사 한 줄을 사람 문장으로. 모르는 액션이어도 **원문을 그대로 보여 준다**.

    빈 문자열이나 '알 수 없는 활동' 으로 뭉개지 않는다 — 내가 한 일인데 무엇인지 알 수
    없게 만드는 것이 이 화면에서 할 수 있는 가장 나쁜 일이다. 원문이라도 보이면
    사용자는 최소한 검색해서 물어볼 수 있다.
    """
    sentence = ACTION_SENTENCES.get(action)
    if sentence:
        return sentence
    parts = (action or "").split(".")
    verb = VERB_LABELS.get(parts[-1]) if parts else None
    noun = OBJECT_LABELS.get(object_type or "")
    if verb and noun:
        return f"{noun}{object_particle(noun)} {verb}"
    if verb and action:
        # 동사만 알고 대상을 모르면 동사만 내지 않는다 — "만듦" 한 단어는 무엇을 만들었는지
        # 알려 주지 않아 원문보다도 정보가 적다. 원문을 함께 남긴다.
        return f"{verb} ({action})"
    if noun:
        return f"{noun}: {action}"
    return action or "활동"


def route_for(object_type: str | None, object_id: str | None) -> str | None:
    """딥링크 경로. 알림 표를 먼저 묻고, 없으면 감사 전용 표를 본다."""
    route = destination_for(object_type, object_id)
    if route:
        return route
    template = AUDIT_DESTINATIONS.get(object_type or "")
    if not template:
        return None
    if "{id}" in template:
        if not object_id:
            return None
        # id 는 서버가 만든 값이지만 경로를 깨뜨릴 문자는 통과시키지 않는다.
        if any(ch in object_id for ch in "/?#\\ "):
            return None
        return template.replace("{id}", object_id)
    return template


def _audit_item(row: AuditLog) -> dict:
    return {
        "id": "audit:" + row.id,
        "kind": KIND_DID,
        "at": row.created_at.isoformat(),
        "action": row.action,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "title": describe_action(row.action, row.object_type),
        "body": None,
        # 실패한 시도도 내 활동이다(로그인 실패·비밀번호 오답). 숨기면 "내가 안 했는데
        # 누가 시도했나"를 본인이 알아챌 유일한 창이 닫힌다.
        "result": row.result,
        "route": route_for(row.object_type, row.object_id),
        "read_at": None,
    }


def _notification_item(row: Notification) -> dict:
    return {
        "id": "noti:" + row.id,
        "kind": KIND_HAPPENED,
        "at": row.created_at.isoformat(),
        "action": row.type,
        "object_type": row.related_object_type,
        "object_id": row.related_object_id,
        "title": row.title,
        "body": row.body,
        "result": "success",
        "route": route_for(row.related_object_type, row.related_object_id),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


def build_feed(
    db: Session, user_id: str, *, kind: str | None = None, offset: int = 0, limit: int = 20
) -> dict:
    """두 원천을 합쳐 시간 역순으로 자른다.

    각 원천에서 `offset + limit` 건만 읽는다 — 합친 뒤 자를 것이므로 그보다 더 읽어도
    결과가 달라지지 않고, 무제한으로 읽으면 오래 쓴 계정에서 응답이 통째로 커진다.
    `total` 은 정확한 합계다(개수는 따로 센다) — 목록은 잘려도 "몇 건인지"는 진실이어야
    한다(app/home/aggregate.py 의 bucket 과 같은 규칙).
    """
    take = max(offset + limit, 1)
    items: list[dict] = []
    total = 0

    if kind in (None, "", KIND_DID):
        rows = (
            db.execute(
                select(AuditLog)
                .where(AuditLog.user_id == user_id)
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                .limit(take)
            ).scalars().all()
        )
        items.extend(_audit_item(r) for r in rows)
        total += _count(db, AuditLog, AuditLog.user_id == user_id)

    if kind in (None, "", KIND_HAPPENED):
        rows = (
            db.execute(
                select(Notification)
                .where(Notification.user_id == user_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(take)
            ).scalars().all()
        )
        items.extend(_notification_item(r) for r in rows)
        total += _count(db, Notification, Notification.user_id == user_id)

    # 같은 시각이면 id 로 안정 정렬한다 — 페이지를 넘길 때 항목이 왔다 갔다 하지 않게.
    items.sort(key=lambda it: (it["at"], it["id"]), reverse=True)
    return {
        "items": items[offset:offset + limit],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def _count(db: Session, model, condition) -> int:
    from sqlalchemy import func

    return int(
        db.execute(select(func.count()).select_from(model).where(condition)).scalar_one()
    )
