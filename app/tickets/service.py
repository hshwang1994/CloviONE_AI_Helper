"""사용자 셀프서비스 티켓 조회 (내 티켓 / 미할당 / 배정 후보).

Notion '작업' DB 조회 배관은 app/reports/notion_source 를 그대로 재사용한다(OutboundClient 단일
관문, allowlist=services, secret=notion_report_token_ref). 이 모듈은 '로그인 사용자 기준' 필터와
이름 해석만 담당한다.

보안(스펙 §12.3): 대상 notion_user_id 는 **세션 사용자에서만** 도출한다. 브라우저가 notion id 를
주지 않으므로 사용자는 언제나 자기 것만 볼 수 있다(IDOR 원천 차단).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, ValidationAppError
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.reports import notion_source
from app.reports.service import STATUS_CANCELLED, STATUS_DONE, _load_name_map
from app.tickets import notion_write
from app.users.models import (
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_SYSTEM_ADMIN,
    User,
)

# 완료·취소는 '끝난' 티켓 — 미할당 목록의 기본에서 뺀다(진행/계획/이슈/검증만 담당자 필요).
_TERMINAL = {STATUS_DONE, STATUS_CANCELLED}

# 소유권을 우회해 아무 티켓이나 편집할 수 있는 역할(운영/관리자군). 그 외(user/auditor)는
# 본인 담당이거나 미할당인 티켓만 편집할 수 있다(IDOR 차단).
_EDIT_BYPASS_ROLES = {ROLE_OPERATOR, ROLE_ADMIN, ROLE_SYSTEM_ADMIN}

# 편집 가능한 필드 → 작업 DB 속성명 후보(rename 대비 별칭). notion_source 의 상수와 일치.
_EDIT_PROP_ALIASES = {
    "status": [notion_source.PROP_STATUS, "진행 상태"],
    "difficulty": [notion_source.PROP_DIFFICULTY],
    "priority": [notion_source.PROP_PRIORITY],
    "est_wd": [notion_source.PROP_EST],
    "due_date": [notion_source.PROP_DUE],
    "assignee_user_ids": [notion_source.PROP_PEOPLE],
}

# 감사 before/after 스냅샷에 담는 티켓 필드(값만 — secret 아님).
_SNAPSHOT_KEYS = ("status", "due", "assignees", "est_wd", "difficulty", "priority")


def my_notion_id(db: Session, user: User) -> str | None:
    """로그인 사용자의 verified Notion user id(정방향). 매핑이 없거나 미검증이면 None.

    reports 의 _load_name_map 은 역방향(notion id → 이름)이라 여기엔 못 쓴다 — 정방향 전용.
    """
    row = db.execute(
        select(UserNotionMapping.notion_user_id).where(
            UserNotionMapping.user_id == user.id,
            UserNotionMapping.status == STATUS_VERIFIED,
        )
    ).first()
    return row[0] if row and row[0] else None


def _verified_id_to_user(db: Session) -> dict[str, str]:
    """verified·active 매핑의 notion_user_id → 앱 user_id. 담당자 편집(해석/보존/역표시)에 쓴다.

    _load_name_map 은 표시용 이름(전 사용자 포함)이라 편집엔 못 쓴다 — 편집 후보/보존 판정은
    반드시 'verified + active' 로만 한다(스펙 §12.3).
    """
    rows = db.execute(
        select(UserNotionMapping.notion_user_id, User.id)
        .join(User, User.id == UserNotionMapping.user_id)
        .where(
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
            User.active.is_(True),
            User.archived_at.is_(None),
        )
    ).all()
    out: dict[str, str] = {}
    for nid, uid in rows:
        out.setdefault(nid, uid)
    return out


def _project_names_map(outbound, settings) -> dict[str, str]:
    """프로젝트 페이지 id → 이름. 티켓의 '프로젝트' relation 을 사람이 읽는 이름으로 바꾼다(그룹핑용).

    프로젝트 조회 실패(토큰/네트워크)는 치명적이지 않다 — 이름 없이 티켓만이라도 보이게 빈 맵으로 흘린다.
    """
    try:
        rows = list_projects(outbound, settings)  # [{id, name}] — 스키마의 프로젝트 relation 대상 DB 조회
    except Exception:
        return {}
    return {r["id"]: (r.get("name") or "") for r in rows if r.get("id")}


def _enrich(tickets: list[dict], id_to_name: dict[str, str], id_to_user: dict[str, str],
            proj_map: dict[str, str] | None = None) -> list[dict]:
    """각 티켓에 담당자 이름/앱 user_id, 그리고 프로젝트 이름(project_names/project)을 붙인다.

    assignee_names 는 표시용(전 사용자 이름 맵), assignee_user_ids 는 verified·active 매핑만.
    project 는 그룹핑용 대표 프로젝트명(첫 relation), project_names 는 전체(다중 프로젝트 대비).
    """
    proj_map = proj_map or {}
    out = []
    for t in tickets:
        assignees = t.get("assignees") or []
        names = [id_to_name.get(a) for a in assignees]
        uids = [id_to_user.get(a) for a in assignees]
        pnames = [proj_map.get(pid) for pid in (t.get("project_ids") or [])]
        pnames = [n for n in pnames if n]
        out.append({
            **t,
            "assignee_names": [n for n in names if n],
            "assignee_user_ids": [u for u in uids if u],
            "project_names": pnames,
            "project": pnames[0] if pnames else "",
        })
    return out


def list_my_tickets(db: Session, outbound, settings, user: User) -> dict:
    """로그인 사용자가 담당한 티켓 전부(마감 무관). 매핑이 없으면 {mapped: False}."""
    nid = my_notion_id(db, user)
    if not nid:
        return {"mapped": False, "tickets": []}
    rows = notion_source.query_tasks_by_assignee(outbound, settings, notion_user_id=nid)
    id_to_name, _ = _load_name_map(db)
    return {"mapped": True, "tickets": _enrich(rows, id_to_name, _verified_id_to_user(db), _project_names_map(outbound, settings))}


def list_unassigned_tickets(db: Session, outbound, settings, *, active_only: bool = True) -> list[dict]:
    """담당자가 없는 티켓. 기본은 활성(완료·취소 제외)만 — 아직 사람이 필요한 일."""
    rows = notion_source.query_unassigned_tasks(outbound, settings)
    if active_only:
        rows = [t for t in rows if (t.get("status") or "") not in _TERMINAL]
    # 미할당도 프로젝트별로 묶어 보이게 프로젝트 이름을 붙인다(담당자는 없음).
    return _enrich(rows, {}, {}, _project_names_map(outbound, settings))


def list_assignees(db: Session) -> list[dict]:
    """담당자로 배정 가능한 사람 목록 — active + verified 매핑 사용자의 {user_id, display_name}.

    raw notion_user_id 는 응답에 넣지 않는다(브라우저 미노출, 스펙 §12.3). 편집 API 가 user_id 를
    받아 서버에서 notion id 로 해석한다.
    """
    rows = db.execute(
        select(User.id, User.display_name)
        .join(UserNotionMapping, UserNotionMapping.user_id == User.id)
        .where(
            User.active.is_(True),
            User.archived_at.is_(None),
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
        )
        .order_by(User.display_name)
    ).all()
    return [{"user_id": uid, "display_name": name} for uid, name in rows]


# ── 수동 편집(쓰기) ────────────────────────────────────────────────────────────

def _snapshot(ticket: dict) -> dict:
    """감사 before/after 용 티켓 값 스냅샷(secret 아님)."""
    return {k: ticket.get(k) for k in _SNAPSHOT_KEYS}


def _schema_prop(schema: dict, names: list[str]) -> tuple[str | None, dict | None]:
    for n in names:
        p = schema.get(n)
        if isinstance(p, dict):
            return n, p
    return None, None


def ensure_can_edit(ticket: dict, user: User, my_notion_id_value: str | None) -> None:
    """소유권 검증(스펙 §25.5·IDOR). 운영/관리자군은 우회, 그 외는 본인 담당 또는 미할당만.

    Notion 에서 방금 읽은 '현재' 티켓의 담당자로 판정한다(프런트가 준 값이 아니라).
    """
    if user.role in _EDIT_BYPASS_ROLES:
        return
    assignees = ticket.get("assignees") or []
    if not assignees:
        return  # 미할당 — 담당자가 필요한 일이므로 누구나 손댈 수 있다(배정 포함)
    if my_notion_id_value and my_notion_id_value in assignees:
        return  # 본인 담당
    raise ForbiddenError("이 티켓을 편집할 권한이 없습니다(담당자 또는 미할당 티켓만 편집할 수 있습니다).")


def _resolve_assignee_ids(db: Session, user_ids: list[str]) -> list[str]:
    """앱 user_id 목록 → Notion user_id 목록(verified·active 매핑만). 하나라도 해석 불가면 거절.

    브라우저는 절대 Notion id 를 주지 않는다 — 항상 서버에서 매핑으로 해석한다(스펙 §12.3).
    """
    if not user_ids:
        return []
    rows = db.execute(
        select(User.id, UserNotionMapping.notion_user_id)
        .join(UserNotionMapping, UserNotionMapping.user_id == User.id)
        .where(
            User.id.in_(user_ids),
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
            User.active.is_(True),
            User.archived_at.is_(None),
        )
    ).all()
    found = {uid: nid for uid, nid in rows}
    missing = [uid for uid in user_ids if uid not in found]
    if missing:
        raise ValidationAppError("담당자로 지정할 수 없는 사용자가 있습니다(Notion 계정 미연결).")
    seen: set[str] = set()
    out: list[str] = []
    for uid in user_ids:
        nid = found[uid]
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return out


def _build_assignee_people(db: Session, current_assignees: list[str], user_ids: list[str]) -> list[str]:
    """새 담당자(people) notion id 목록을 만든다.

    앱에 연결되지 않은(verified 매핑이 없는) 기존 담당자는 **보존**하고, 앱 사용자 담당자만
    user_ids 로 교체한다 — 이렇게 하면 편집 화면(앱 사용자 체크박스)으로 손대지 않은 외부/미연결
    담당자를 조용히 지우지 않는다.
    """
    id_to_user = _verified_id_to_user(db)  # verified·active notion id 전체
    mapped_ids = set(id_to_user)
    preserved = [nid for nid in current_assignees if nid not in mapped_ids]
    resolved = _resolve_assignee_ids(db, user_ids)
    merged: list[str] = []
    seen: set[str] = set()
    for nid in preserved + resolved:
        if nid not in seen:
            seen.add(nid)
            merged.append(nid)
    return merged


def update_ticket(db: Session, outbound, settings, user: User, *, page_id: str, changes: dict) -> dict:
    """티켓 속성을 수동 편집한다(소유권·스키마 검증 후 Notion PATCH). 감사용 before/after 포함.

    changes 는 이미 exclude_unset 된 dict(보낸 필드만). 각 값은 스키마 타입/허용옵션으로 검증한다.
    """
    if not changes:
        raise ValidationAppError("변경할 내용이 없습니다.")

    current = notion_write.fetch_ticket(outbound, settings, page_id)
    ensure_can_edit(current, user, my_notion_id(db, user))

    schema = notion_write.fetch_schema(outbound, settings)
    properties: dict = {}
    for key, value in changes.items():
        names = _EDIT_PROP_ALIASES.get(key)
        if not names:
            continue  # 알 수 없는 키(스키마가 forbid 하므로 실제로는 오지 않음)
        pname, prop = _schema_prop(schema, names)
        if not prop:
            raise ValidationAppError(f"작업 DB에서 '{names[0]}' 속성을 찾지 못했습니다.")

        if key == "assignee_user_ids":
            people = _build_assignee_people(db, current.get("assignees") or [], value or [])
            mapped = notion_write.property_value(prop, people)
        elif key == "status":
            if not value:
                raise ValidationAppError("진행상태는 비울 수 없습니다.")
            allowed = notion_write.option_names(prop)
            if allowed and value not in allowed:
                raise ValidationAppError(f"진행상태 값이 올바르지 않습니다. 허용: {', '.join(allowed)}")
            mapped = notion_write.property_value(prop, value)
        elif key in ("difficulty", "priority"):
            if value:
                allowed = notion_write.option_names(prop)
                if allowed and value not in allowed:
                    label = "난이도" if key == "difficulty" else "우선순위"
                    raise ValidationAppError(f"{label} 값이 올바르지 않습니다. 허용: {', '.join(allowed)}")
            mapped = notion_write.property_value(prop, value)  # 빈 값 → select 지움
        else:  # est_wd, due_date
            mapped = notion_write.property_value(prop, value)

        if mapped is None:
            raise ValidationAppError(f"'{names[0]}' 값을 적용할 수 없습니다.")
        properties[pname] = mapped

    updated = notion_write.update_ticket_properties(outbound, settings, page_id=page_id, properties=properties)
    id_to_name, _ = _load_name_map(db)
    ticket = _enrich([updated], id_to_name, _verified_id_to_user(db))[0]
    return {"ticket": ticket, "before": _snapshot(current), "after": _snapshot(updated)}


def claim_ticket(db: Session, outbound, settings, user: User, *, page_id: str) -> dict:
    """미할당(또는 본인 담당) 티켓의 담당자에 '나'를 배정한다. 내 계정이 Notion 미연결이면 거절."""
    if not my_notion_id(db, user):
        raise ValidationAppError("내 계정이 Notion 사용자와 연결되어 있지 않아 담당자로 배정할 수 없습니다.")
    return update_ticket(db, outbound, settings, user, page_id=page_id, changes={"assignee_user_ids": [user.id]})


def list_projects(outbound, settings) -> list[dict]:
    """새 티켓 폼의 프로젝트 드롭다운용 [{id, name}]. 작업 DB 스키마의 '프로젝트' relation 대상 DB를
    자동 발견해 조회한다(별도 설정 상수 없이 — relation.database_id 사용).

    프로젝트 속성이 relation 이 아니거나 없으면 빈 목록(폼은 프로젝트 선택을 생략한다).
    """
    schema = notion_write.fetch_schema(outbound, settings)
    _, prop = _schema_prop(schema, ["프로젝트"])
    db_id = notion_write.relation_target_db(prop) if prop else None
    if not db_id:
        return []
    rows = notion_write.query_relation_titles(outbound, settings, db_id)
    # 이름 있는 것 먼저, 이름 기준 정렬. 이름 없는(제목 빈) 프로젝트는 뒤로.
    rows = [r for r in rows if r.get("id")]
    rows.sort(key=lambda r: (r.get("name") or "￿"))
    return rows


def create_ticket(db: Session, outbound, settings, user: User, *, payload) -> dict:
    """새 티켓을 만든다(제목 필수). 담당자는 user_id→notion id 해석, 프로젝트는 relation.

    상태/우선순위/난이도는 실제 스키마 옵션으로 검증한다. 진행상태 미지정 시 '계획'(없으면 첫 옵션).
    프로젝트 속성이 스키마에 있으면 project_id 를 필수로 요구한다(고아 티켓 방지).
    """
    schema = notion_write.fetch_schema(outbound, settings)
    properties: dict = {}

    # 제목(필수)
    tname, tprop = _schema_prop(schema, ["제목"])
    if not tprop:
        raise ValidationAppError("작업 DB에서 '제목' 속성을 찾지 못했습니다.")
    properties[tname] = notion_write.property_value(tprop, payload.title)

    # 진행상태(기본 계획)
    sname, sprop = _schema_prop(schema, [notion_source.PROP_STATUS, "진행 상태"])
    if sprop:
        options = notion_write.option_names(sprop)
        status_val = payload.status or None
        if status_val:
            if options and status_val not in options:
                raise ValidationAppError(f"진행상태 값이 올바르지 않습니다. 허용: {', '.join(options)}")
        else:
            status_val = "계획" if (not options or "계획" in options) else options[0]
        mapped = notion_write.property_value(sprop, status_val)
        if mapped is not None:
            properties[sname] = mapped

    # 선택 옵션(우선순위·난이도)
    for key, label, aliases in (
        ("priority", "우선순위", [notion_source.PROP_PRIORITY]),
        ("difficulty", "난이도", [notion_source.PROP_DIFFICULTY]),
    ):
        val = getattr(payload, key, None)
        if not val:
            continue
        pname, prop = _schema_prop(schema, aliases)
        if not prop:
            continue
        options = notion_write.option_names(prop)
        if options and val not in options:
            raise ValidationAppError(f"{label} 값이 올바르지 않습니다. 허용: {', '.join(options)}")
        properties[pname] = notion_write.property_value(prop, val)

    # 예상 WD / 마감일
    if payload.est_wd is not None:
        ename, eprop = _schema_prop(schema, [notion_source.PROP_EST])
        if eprop:
            properties[ename] = notion_write.property_value(eprop, payload.est_wd)
    if payload.due_date:
        dname, dprop = _schema_prop(schema, [notion_source.PROP_DUE])
        if dprop:
            properties[dname] = notion_write.property_value(dprop, payload.due_date)

    # 담당자(user_id → notion id)
    if payload.assignee_user_ids:
        pname, pprop = _schema_prop(schema, [notion_source.PROP_PEOPLE])
        if pprop:
            people = _resolve_assignee_ids(db, payload.assignee_user_ids)
            properties[pname] = notion_write.property_value(pprop, people)

    # 프로젝트(스키마에 있으면 필수)
    prj_name, prj_prop = _schema_prop(schema, ["프로젝트"])
    if prj_prop and notion_write.relation_target_db(prj_prop):
        if not payload.project_id:
            raise ValidationAppError("프로젝트를 선택하세요.")
        properties[prj_name] = notion_write.property_value(prj_prop, [payload.project_id])

    # 설명도 문서 본문처럼 가벼운 마크다운(제목/글머리/번호/구분선)을 Notion 블록으로 변환한다
    # (프런트 BodyEditor 미리보기와 동일 규칙). 빈 설명이면 children 없음.
    from app.core.notion_blocks import markdown_to_blocks

    children = markdown_to_blocks(payload.description) if payload.description else None
    created = notion_write.create_page(
        outbound, settings,
        parent_database_id=settings.notion_tasks_database_id,
        properties=properties, children=children,
    )
    id_to_name, _ = _load_name_map(db)
    ticket = _enrich([created], id_to_name, _verified_id_to_user(db))[0]
    return {"ticket": ticket, "after": _snapshot(created)}


def ticket_meta(outbound, settings) -> dict:
    """편집 드롭다운용 허용 옵션(진행상태·우선순위·난이도)을 작업 DB 스키마에서 읽어 돌려준다.

    하드코딩 대신 실제 스키마에서 읽어 Notion 옵션 rename 과 항상 일치하게 한다.
    """
    schema = notion_write.fetch_schema(outbound, settings)

    def opts(names: list[str]) -> list[str]:
        _, prop = _schema_prop(schema, names)
        return notion_write.option_names(prop) if prop else []

    return {
        "statuses": opts(_EDIT_PROP_ALIASES["status"]),
        "priorities": opts(_EDIT_PROP_ALIASES["priority"]),
        "difficulties": opts(_EDIT_PROP_ALIASES["difficulty"]),
    }
