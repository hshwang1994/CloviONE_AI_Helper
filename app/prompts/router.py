"""Prompt and Policy version-management API (spec §17, §23.5).

NOTE: no ``from __future__ import annotations`` here — the router factory
annotates endpoint params with closure variables (``payload: create_schema``),
which must stay real class objects for FastAPI to see them as request bodies.
"""

import json as _json

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator


def _json_object_to_str(value: object) -> object:
    """관리자 콘솔의 JSON 입력 필드는 파싱된 객체(dict/list)를 보낸다. 백엔드는 JSON 문자열을
    저장(content_json)하므로 여기서 직렬화해 둘 다(콘솔=객체, 외부 API=문자열)를 받는다.
    빈 값(None)은 빈 객체로 본다. 문자열은 그대로 둔다 — 프롬프트 본문(자유 텍스트)은 영향 없다."""
    if isinstance(value, (dict, list)):
        return _json.dumps(value, ensure_ascii=False)
    if value is None:
        return "{}"
    return value
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES
from app.core.db import is_insert_race
from app.core.deps import get_db, get_principal, require_csrf, require_roles
from app.ai.prompts import catalog as prompt_catalog
from app.ai.prompts import service as prompt_slots
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.scope import Principal, require_global_management
from app.prompts.models import STATUS_DRAFT, STATUS_PUBLISHED, Policy, Prompt
from app.prompts.service import (
    diff_versions,
    get_or_404,
    new_version_from,
    next_version,
    rollback_to_version,
    transition,
    update_draft,
    validate_policy_content,
)

# 기본 제공 행의 id 머리(D-518). 표에 없는 가상 행이라 이 머리로만 알아본다.
BUILTIN_PREFIX = "builtin:"
STATUS_BUILTIN = "builtin"
USAGE_WINDOW_DAYS = 30


# 화면에 그대로 나가는 주어다 — `require_global_management` 가 받침을 보고 조사를 붙인다
# ("프롬프트는 전체 범위 관리자만 바꿀 수 있습니다.").
_GLOBAL_SUBJECT = {"prompts": "프롬프트", "policies": "정책"}


def _clean_name(value: str) -> str:
    """이름은 공백만으로 이뤄질 수 없고, 앞뒤 공백은 이름의 일부가 아니다.

    `app/org/service.py::normalize_name` 이 부서·직책에 쓰는 규칙과 같은 규칙이다. 여기만
    비어 있으면 두 가지가 깨진다. 첫째, 목록·사용 통계·이름 필터에 이름 칸이 빈 행이 남아
    관리자가 그 행을 가리킬 방법이 없다. 둘째, ' 티켓 요약' 과 '티켓 요약' 이 서로 다른
    이름이 되어 같은 이름을 막는 중복 검사(409)와 버전 묶음이 그대로 갈라진다.
    """
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("이름을 입력해야 합니다.")
    return cleaned


def _clean_slot(value: str | None) -> str | None:
    """사용처는 목록에 있는 값이어야 하고 바꿀 수 있는 사용처여야 한다. 비우면 「아직 정하지 않음」이다."""
    cleaned = (value or "").strip() or None
    problem = prompt_slots.slot_problem(cleaned)
    if problem:
        raise ValueError(problem)
    return cleaned


class PromptCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="", max_length=100000)
    # 사용처(D-518). 초안은 비워 둘 수 있고 발행할 때 반드시 있어야 한다.
    slot: str | None = Field(default=None, max_length=32)

    _normalize_name = field_validator("name")(_clean_name)
    _check_slot = field_validator("slot")(_clean_slot)


class PolicyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # WF1 단독 결함 — Prompt와 대칭. app/prompts/models.py::Policy.purpose(0058) 참고.
    purpose: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="{}", max_length=100000)
    # 종류와 적용 대상(D-519). 종류는 만들 때 정하고 바꾸지 않는다 - 바꾸면 규칙의 칸이 통째로 달라진다.
    kind: str = Field(min_length=1, max_length=24)
    applies_to: list[str] | str = Field(default="*")

    _normalize_name = field_validator("name")(_clean_name)
    _coerce_content = field_validator("content", mode="before")(_json_object_to_str)


# UB-22: 예전엔 이 하나(ContentUpdateRequest)를 prompts/policies 둘 다에 썼다.
# `_json_object_to_str`의 `None → "{}"` 분기가 콘솔의 "빈 JSON 입력란"(Policy)을 위한
# 것인데 타입 게이트가 없어, `PATCH prompts/{id} {"content": null}`(자유 텍스트여야
# 하는 Prompt 본문)도 그대로 통과해 422 검증 오류 대신 **문자열 리터럴 "{}"가 본문에
# 저장**됐다 - create() 이 이미 kind별로 스키마를 나눠 두고 있던 것(PromptCreateRequest/
# PolicyCreateRequest)과 같은 모양으로 patch()도 나눈다.
#
# 🔴 PATCH 는 **부분 갱신**이다 — 아래 두 스키마의 기본값은 저장 경로에 절대 닿지 않는다.
# 콘솔(DataScreen)은 바뀐 필드만 보낸다. 예전에는 정책의 `content` 기본값 `"{}"` 가 그대로
# 저장돼, 「용도」한 줄만 고쳐도 규칙 전체가 빈 객체로 지워지고 응답은 200 이었다(같은 요청이
# 프롬프트에서는 `content` 가 필수라 422 였다 — 쌍둥이 화면의 답이 서로 달랐다). 그래서
# 보낸 칸은 `model_fields_set` 으로만 판정하고(`_sent_changes`), 안 보낸 칸은 손대지 않는다.
class PromptContentUpdateRequest(BaseModel):
    content: str = Field(default="", max_length=100000)
    purpose: str | None = Field(default=None, max_length=2000)
    slot: str | None = Field(default=None, max_length=32)

    _check_slot = field_validator("slot")(_clean_slot)


class PolicyContentUpdateRequest(BaseModel):
    purpose: str | None = Field(default=None, max_length=2000)
    content: str = Field(default="{}", max_length=100000)
    applies_to: list[str] | str | None = Field(default=None)

    _coerce_content = field_validator("content", mode="before")(_json_object_to_str)


def _sent_changes(payload: BaseModel) -> dict:
    """요청 본문에 **실제로 실려 온 칸만** 뽑는다.

    `payload.content` 를 그냥 읽으면 「안 보냈다」와 「기본값」이 같은 값으로 보여 구별할 수
    없다. `model_fields_set` 은 그 둘을 가르는 유일한 근거다(`app/knowledge/schemas.py::
    DocumentSave.category_id` 가 같은 규약을 쓴다). `purpose` 의 `null` 은 「용도를 지운다」는
    뜻으로 받는다 — 안 보낸 것과 다른 사실이다.
    """
    sent = payload.model_fields_set
    return {field: getattr(payload, field) for field in ("content", "purpose", "slot", "applies_to")
            if field in sent}


class TransitionRequest(BaseModel):
    status: str


class RollbackRequest(BaseModel):
    # UB-30: 형제 엔드포인트 diff()의 name 쿼리 파라미터는 이미 max_length=120(Prompt/
    # Policy.name의 DB 컬럼 String(120)과 같은 값)을 걸어 두는데 여기만 무제한이었다.
    name: str = Field(max_length=120)
    version: int


# created_by is stored as a raw user id. Every view below also exposes
# created_by_name/created_by_email (resolved via _resolve_creator_names,
# same pattern as the audit log's actor_name) so the admin console can show
# a display name instead of a bare UUID — created_by itself is kept for API
# stability.
def _creator_fields(created_by: str | None, names: dict) -> dict:
    creator = names.get(created_by, {}) if created_by else {}
    return {
        "created_by": created_by,
        "created_by_name": creator.get("display_name"),
        "created_by_email": creator.get("email"),
    }


def _frame(slot) -> dict | None:
    """사용처가 코드에 고정한 틀 - 관리자가 바꿀 수 없는 역할 문장과 출력 형식(화면이 읽기 전용으로 보인다)."""
    if slot is None:
        return None
    return {"role": slot.role, "format_line": slot.format_line, "grounding": slot.grounding}


def _usage_fields(usage: dict | None) -> dict:
    usage = usage or {}
    return {"calls_30d": int(usage.get("calls", 0)), "last_used_at": usage.get("last_at")}


def _prompt_view(row: Prompt, names: dict | None = None, usage: dict | None = None) -> dict:
    slot = prompt_catalog.SLOTS.get(row.slot) if row.slot else None
    return {
        "id": row.id,
        "name": row.name,
        "purpose": row.purpose,
        "version": row.version,
        "content": row.content,
        "status": row.status,
        "slot": row.slot,
        "slot_label": slot.label if slot else None,
        "source": prompt_slots.SOURCE_ADMIN,
        # 발행은 「이 사용처에서 다음 호출부터 쓴다」는 뜻이다(사용처마다 하나, D-518).
        "in_use": row.status == STATUS_PUBLISHED and slot is not None and slot.editable,
        "frame": _frame(slot),
        **_creator_fields(row.created_by, names or {}),
        "created_at": row.created_at.isoformat(),
        "published_at": row.published_at.isoformat() if row.published_at else None,
        **_usage_fields(usage),
    }


def _builtin_view(slot, *, in_use: bool, usage: dict | None = None) -> dict:
    """기본 제공 지시문 한 줄. 표에 없는 가상 행이다 - 고칠 수 없고 「복제해서 수정」으로 초안을 만든다."""
    return {
        "id": BUILTIN_PREFIX + slot.key,
        "name": slot.label,
        "purpose": slot.description,
        "version": None,
        "content": slot.instruction,
        "status": STATUS_BUILTIN,
        "slot": slot.key,
        "slot_label": slot.label,
        "source": prompt_slots.SOURCE_BUILTIN,
        "in_use": in_use,
        "editable": slot.editable,
        "frame": _frame(slot),
        "created_by": None,
        "created_by_name": None,
        "created_by_email": None,
        "created_at": None,
        "published_at": None,
        **_usage_fields(usage),
    }


def _published_slots(db: Session) -> dict[str, Prompt]:
    rows = db.execute(
        select(Prompt).where(Prompt.status == STATUS_PUBLISHED, Prompt.slot.is_not(None))
    ).scalars().all()
    return {row.slot: row for row in rows}


def _usage_since(request: Request):
    from datetime import timedelta

    return request.app.state.clock.now() - timedelta(days=USAGE_WINDOW_DAYS)


def _policy_targets(row: Policy) -> list[str]:
    try:
        value = _json.loads(row.applies_to_json or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _target_labels(targets: list[str]) -> list[str]:
    from app.ai.actions import ACTIONS

    return ["모든 기능" if t == "*" else (ACTIONS[t].label if t in ACTIONS else t) for t in targets]


def _policy_view(row: Policy, names: dict | None = None, usage: dict | None = None) -> dict:
    import json

    from app.ai.policy.schemas import KIND_LABELS, KIND_LEGACY

    targets = _policy_targets(row)
    return {
        "id": row.id,
        "name": row.name,
        "purpose": row.purpose,
        "version": row.version,
        "content": json.loads(row.content_json),
        "kind": row.kind,
        "kind_label": KIND_LABELS.get(row.kind, row.kind),
        "applies_to": targets,
        "applies_to_labels": _target_labels(targets),
        "migrated_from_id": row.migrated_from_id,
        # 발행한 정책은 다음 AI 요청부터 걸린다(D-519). 옛 형식은 발행될 수 없다.
        "in_use": row.status == STATUS_PUBLISHED and row.kind != KIND_LEGACY,
        **_usage_fields(usage),
        "status": row.status,
        **_creator_fields(row.created_by, names or {}),
        "created_at": row.created_at.isoformat(),
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


def _resolve_creator_names(db: Session, ids) -> dict:
    from app.users.models import User

    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    result: dict[str, dict[str, str]] = {}
    for u in db.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(wanted))
    ).all():
        result[u.id] = {"display_name": u.display_name, "email": u.email}
    return result


# ── 프롬프트에만 있는 경로 (D-518) ──────────────────────────────────────────────
#
# 사용처 목록과 「복제해서 수정」. 공장 함수(`_build_router`) 밖의 맨 위 수준 라우터에 둔다. 앱이 이 라우터를
# `prompts_router` 보다 **먼저** 건다(`app/main.py`) - 한 토막짜리 경로(`/slots`)가 뒤에 오면 `/{row_id}` 가
# `row_id="slots"` 로 먼저 잡는다.
prompt_slots_router = APIRouter(
    prefix="/api/admin/prompts",
    tags=["admin-prompts"],
    dependencies=[Depends(require_csrf)],
)


@prompt_slots_router.get("/slots", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
def prompt_slots_list(db: Session = Depends(get_db)):
    """사용처 목록. 화면의 사용처 고르기와 기본 문구 보기가 이 값을 쓴다 - 이름을 화면이 지어내지 않는다."""
    published = _published_slots(db)
    items = []
    for entry in prompt_catalog.SLOTS.values():
        current = published.get(entry.key) if entry.editable else None
        items.append({
            "key": entry.key, "label": entry.label, "description": entry.description,
            "instruction": entry.instruction, "editable": entry.editable, "frame": _frame(entry),
            "published": {"id": current.id, "name": current.name, "version": current.version} if current else None,
        })
    return {"items": items}


@prompt_slots_router.post("/builtin/{slot_key}/copy", status_code=201,
                          dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
def copy_builtin_prompt(
    request: Request,
    slot_key: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """기본 제공 지시문을 초안으로 옮긴다. 같은 이름이 이미 있으면 그 이름의 새 버전이 된다."""
    require_global_management(principal, _GLOBAL_SUBJECT["prompts"])
    entry = prompt_catalog.SLOTS.get(slot_key)
    if entry is None:
        raise NotFoundError("알 수 없는 사용처입니다.")
    problem = prompt_slots.slot_problem(slot_key)
    if problem:
        raise ValidationAppError(problem)
    name = f"{entry.label} 지시문"
    try:
        with db.begin_nested():
            row = Prompt(
                name=name, purpose=entry.description, version=next_version(db, Prompt, name),
                content=entry.instruction, slot=entry.key, status=STATUS_DRAFT,
                created_by=request.state.user.id,
            )
            db.add(row)
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_insert_race(exc):
            raise
        raise ConflictError("같은 이름의 버전을 거의 동시에 만들었습니다. 목록을 다시 불러오세요.") from exc
    record_audit_from_request(
        request, db, action="prompts.create", object_type="prompts", object_id=row.id,
        after={"name": row.name, "version": row.version, "slot": row.slot, "from": "builtin"},
    )
    return {"item": _prompt_view(row, _resolve_creator_names(db, {row.created_by}))}


def _build_router(kind: str, model, view, create_schema, content_update_schema):
    router = APIRouter(
        prefix=f"/api/admin/{kind}",
        tags=[f"admin-{kind}"],
        dependencies=[Depends(require_csrf)],
    )

    def _view_single(db: Session, row) -> dict:
        names = _resolve_creator_names(db, {row.created_by} if row.created_by else set())
        return view(row, names)

    @router.get("", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
    def list_all(
        request: Request,
        db: Session = Depends(get_db),
        name: str | None = Query(default=None, max_length=120),
        status: str | None = Query(default=None, max_length=16),
        # 프롬프트만 쓴다(D-518): 사용처와 출처(기본 제공 · 관리자 작성). 정책 목록은 두 값을 보지 않는다.
        slot: str | None = Query(default=None, max_length=32),
        source: str | None = Query(default=None, max_length=16),
        # 정책만 쓴다(D-519): 종류.
        kind_filter: str | None = Query(default=None, alias="kind", max_length=24),
        page: int = Query(default=1, ge=1),
        # Default kept at the old hardcoded .limit(500) so existing callers
        # (registry.js does not yet set paginated:true / pass page params —
        # see finding) keep seeing everything they used to in one call. What
        # changes is that results are no longer SILENTLY truncated past 500:
        # `total` is now returned so a caller can detect truncation, and a
        # caller that needs more can page explicitly.
        page_size: int = Query(default=500, ge=1, le=500),
    ):
        is_prompt = model is Prompt
        want_builtin = is_prompt and not name and source in (None, "", prompt_slots.SOURCE_BUILTIN) \
            and status in (None, "", STATUS_BUILTIN)
        want_rows = not (is_prompt and (source == prompt_slots.SOURCE_BUILTIN or status == STATUS_BUILTIN))
        stmt = select(model)
        if name:
            stmt = stmt.where(model.name == name)
        if status and status != STATUS_BUILTIN:
            stmt = stmt.where(model.status == status)
        if is_prompt and slot:
            stmt = stmt.where(Prompt.slot == slot)
        if model is Policy and kind_filter:
            stmt = stmt.where(Policy.kind == kind_filter)
        if not want_rows:
            stmt = stmt.where(False)
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = (
            db.execute(
                # 🔴 마지막 절이 PK 다 — **전순서**여야 한다. `(name, version)` 은 실무상
                # 유일하지만 계약으로 보장되지 않고, 전순서가 아니면 OFFSET 페이징이 같은 행을
                # 두 묶음에 내거나 아예 빠뜨린다(그 어긋남은 오류를 안 낸다).
                # 같은 이유를 `app/knowledge/service.py::_order_by` 가 이미 적어 뒀다(Z9).
                stmt.order_by(model.name, model.version.desc(), model.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        names = _resolve_creator_names(db, {r.created_by for r in rows if r.created_by})
        if not is_prompt:
            from app.ai import usage as usage_mod

            applied = usage_mod.policy_usage(db, since=_usage_since(request))
            return {"items": [view(r, names, applied.get(r.id)) for r in rows], "total": total, "page": page,
                    "page_size": page_size}

        # 프롬프트: 사용처마다 기본 제공 행을 앞에 둔다(첫 쪽에만). 발행본이 있는 사용처의 기본 제공 행은 쉬고 있다.
        from app.ai import usage as usage_mod

        by_prompt, by_builtin = usage_mod.prompt_usage(db, since=_usage_since(request))
        builtin_items = []
        if want_builtin:
            published = _published_slots(db)
            for entry in prompt_catalog.SLOTS.values():
                if slot and entry.key != slot:
                    continue
                builtin_items.append(_builtin_view(
                    entry, in_use=not (entry.editable and entry.key in published),
                    usage=by_builtin.get(entry.key),
                ))
        items = (builtin_items if page == 1 else []) + [view(r, names, by_prompt.get(r.id)) for r in rows]
        return {"items": items, "total": total + len(builtin_items), "page": page, "page_size": page_size}

    def _require_global(principal: Principal) -> None:
        """프롬프트와 정책은 **포탈 전체**가 함께 쓰는 자원이라 전역 관리자만 바꾼다.

        부서로 나뉘는 자원이 아니다 — 같은 이름의 발행본 하나를 전 부서가 참조하고, 스케줄이
        그 이름을 가리킨다. 부서 범위 관리자가 발행본을 보관하면 다른 팀의 자동화가 근거를
        잃고, 롤백 한 번으로 전사 AI 지시문이 그 사람이 만든 버전으로 바뀐다. 같은 성격의
        공지(`app/announcements/router.py`)와 전역 쿼터(`app/quotas/router.py`)는 이미
        403 을 내고 있었고, 여기만 열려 있던 것은 설계가 아니라 누락이었다.

        읽기는 좁히지 않는다 — 부서 관리자도 지금 무엇이 쓰이는지 볼 수 있어야 한다.
        """
        require_global_management(principal, _GLOBAL_SUBJECT[kind])

    @router.post("", status_code=201, dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def create(
        request: Request,
        payload: create_schema,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        # Existence check only — a name legitimately has many versions, so
        # limit(1) avoids MultipleResultsFound (which would surface as HTTP 500).
        existing = db.execute(
            select(model.id).where(model.name == payload.name).limit(1)
        ).first()
        if existing is not None:
            raise ConflictError(
                f"이미 존재하는 이름입니다: {payload.name}: new-version을 사용하세요."
            )
        content = payload.content
        if model is Policy:
            from app.ai.policy.schemas import KINDS, normalize_applies_to, normalize_rules

            validate_policy_content(content)
            if payload.kind not in KINDS:
                raise ValidationAppError("정책 종류를 고르세요.")
            rules = normalize_rules(payload.kind, _json.loads(content))
            row = Policy(
                name=payload.name, purpose=payload.purpose, version=1,
                content_json=_json.dumps(rules, ensure_ascii=False), kind=payload.kind,
                applies_to_json=_json.dumps(normalize_applies_to(payload.kind, payload.applies_to)),
                status=STATUS_DRAFT, created_by=request.state.user.id,
            )
        else:
            row = Prompt(
                name=payload.name, purpose=payload.purpose, version=1,
                content=content, slot=payload.slot, status=STATUS_DRAFT,
                created_by=request.state.user.id,
            )
        # UB-21: 위 존재 확인~삽입 사이는 잠기지 않는다(커밋은 요청 끝에 한 번). 같은
        # 이름으로 두 생성 요청이 거의 동시에 오면(더블클릭) 둘 다 "기존 없음"을 보고
        # 각자 version=1 삽입을 시도할 수 있다 - uq_{prompts,policies}_name_version
        # 유일 제약이 진 쪽을 IntegrityError로 막는데, 여태 아무도 안 잡아서 그대로
        # 500으로 샜다. 재시도는 안 한다 - 이건 approvals/new_version_from의 "재시도로
        # 풀리는 경합"이 아니라 "이름이 이미 있다"는 실제 결론이 하나뿐인 경합이라,
        # 위와 같은 메시지로 깨끗한 409를 준다.
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except (IntegrityError, OperationalError) as exc:
            if not is_insert_race(exc):
                raise
            raise ConflictError(
                f"이미 존재하는 이름입니다: {payload.name}: new-version을 사용하세요."
            ) from exc
        record_audit_from_request(
            # 같은 기능 안에서 create만 단수화(kind[:-1])해 'policies'→'policie.create'로 어긋났고,
            # 나머지 액션은 'policies.update_content'처럼 복수였다. object_type과 동일한 kind로
            # 통일해 감사 액션 접두를 일관되게 한다(round16 제품 스윕).
            request, db, action=f"{kind}.create",
            object_type=kind, object_id=row.id, after={"name": row.name, "version": 1},
        )
        return {"item": _view_single(db, row)}

    @router.get("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
    def get_one(row_id: str, request: Request, db: Session = Depends(get_db)):
        if model is Prompt and row_id.startswith(BUILTIN_PREFIX):
            entry = prompt_catalog.SLOTS.get(row_id[len(BUILTIN_PREFIX):])
            if entry is None:
                raise NotFoundError("대상 버전을 찾을 수 없습니다.")
            from app.ai import usage as usage_mod

            _, by_builtin = usage_mod.prompt_usage(db, since=_usage_since(request))
            in_use = not (entry.editable and entry.key in _published_slots(db))
            return {"item": _builtin_view(entry, in_use=in_use, usage=by_builtin.get(entry.key))}
        return {"item": _view_single(db, get_or_404(db, model, row_id))}

    @router.patch("/{row_id}", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def patch(
        request: Request,
        row_id: str,
        payload: content_update_schema,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        row = get_or_404(db, model, row_id)
        # WF1 단독 결함 — purpose는 이제 Prompt/Policy 둘 다 있다.
        changes = _sent_changes(payload)
        if model is Policy:
            from app.ai.policy.schemas import normalize_applies_to, normalize_rules

            if "content" in changes:
                validate_policy_content(changes["content"])
                changes["content"] = _json.dumps(normalize_rules(row.kind, _json.loads(changes["content"])),
                                                 ensure_ascii=False)
            if "applies_to" in changes:
                changes["applies_to"] = normalize_applies_to(row.kind, changes["applies_to"])
        update_draft(db, row, **changes)
        record_audit_from_request(
            request, db, action=f"{kind}.update_content", object_type=kind,
            object_id=row.id, after={"name": row.name, "version": row.version},
        )
        return {"item": _view_single(db, row)}

    @router.post("/{row_id}/transition", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def do_transition(
        request: Request,
        row_id: str,
        payload: TransitionRequest,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        row = get_or_404(db, model, row_id)
        before_status = row.status
        transition(db, row, payload.status, now=request.app.state.clock.now())
        record_audit_from_request(
            request, db, action=f"{kind}.transition", object_type=kind,
            object_id=row.id,
            before={"status": before_status},
            after={"status": row.status, "name": row.name, "version": row.version},
        )
        return {"item": _view_single(db, row)}

    @router.post("/{row_id}/new-version", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def new_version(
        request: Request,
        row_id: str,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        row = get_or_404(db, model, row_id)
        copy = new_version_from(db, row, created_by=request.state.user.id)
        record_audit_from_request(
            request, db, action=f"{kind}.new_version", object_type=kind,
            object_id=copy.id, after={"name": copy.name, "version": copy.version},
        )
        return {"item": _view_single(db, copy)}

    @router.get("/usage/stats", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
    def usage_stats(request: Request, db: Session = Depends(get_db)):
        """사용 통계.

        프롬프트는 **사용처마다 한 줄**이다(D-518): 지금 쓰는 지시문(기본 제공이거나 발행본), 최근 30일의 호출 수,
        실패율, 마지막 사용. 수는 AI 호출 기록(`ai_usage_records`)에서 센다 - 예전에는 스케줄이 이름을 참조하는가를
        셌는데 스케줄은 프롬프트를 가리킬 수 없게 된 지 오래라 언제나 「쓰이지 않음」이었다.

        정책은 이름마다 한 줄이다(D-519): 지금 걸리는 버전, 종류, 적용 대상, 그 정책이 걸린 호출 수와 마지막 적용.
        """
        if model is Prompt:
            from app.ai import usage as usage_mod

            by_slot = usage_mod.slot_usage(db, since=_usage_since(request))
            published = _published_slots(db)
            items = []
            for entry in prompt_catalog.SLOTS.values():
                current = published.get(entry.key) if entry.editable else None
                counts = by_slot.get(entry.key, {})
                calls, errors = int(counts.get("calls", 0)), int(counts.get("errors", 0))
                items.append({
                    "slot": entry.key,
                    "label": entry.label,
                    "description": entry.description,
                    "editable": entry.editable,
                    "current_source": prompt_slots.SOURCE_ADMIN if current else prompt_slots.SOURCE_BUILTIN,
                    "current_id": current.id if current else BUILTIN_PREFIX + entry.key,
                    "current_name": current.name if current else None,
                    "current_version": current.version if current else None,
                    "calls": calls,
                    "errors": errors,
                    "failure_rate": usage_mod.percent(errors, calls),
                    "last_used_at": counts.get("last_at"),
                })
            return {"items": items, "kind": kind, "days": USAGE_WINDOW_DAYS}

        # 정책(D-519): 이름마다 한 줄 - 지금 걸리는 버전, 종류, 적용 대상, 최근 30일에 걸린 호출 수와 마지막 적용.
        # 수는 AI 호출 기록의 `policy_ids_json` 에서 센다(그 호출에 그 정책이 걸렸다).
        from app.ai import usage as usage_mod
        from app.ai.policy.schemas import KIND_LABELS

        applied = usage_mod.policy_usage(db, since=_usage_since(request))
        rows = db.execute(select(model).order_by(model.name, model.version)).scalars().all()
        by_name: dict[str, list] = {}
        for row in rows:
            by_name.setdefault(row.name, []).append(row)

        items = []
        for name, versions in by_name.items():
            published = [v for v in versions if v.status == STATUS_PUBLISHED]
            shown = published[-1] if published else versions[-1]
            counts = [applied[v.id] for v in versions if v.id in applied]
            last = max((c["last_at"] for c in counts if c.get("last_at")), default=None)
            targets = _policy_targets(shown)
            items.append({
                "name": name,
                "id": shown.id,
                "kind": shown.kind,
                "kind_label": KIND_LABELS.get(shown.kind, shown.kind),
                "applies_to_labels": _target_labels(targets),
                "versions": len(versions),
                "published_version": published[-1].version if published else None,
                "latest_status": versions[-1].status,
                "applied": sum(int(c.get("calls", 0)) for c in counts),
                "last_applied_at": last,
            })
        items.sort(key=lambda i: (i["published_version"] is None, -i["applied"], i["name"]))
        return {"items": items, "kind": kind, "days": USAGE_WINDOW_DAYS}

    @router.get("/diff/view", dependencies=[Depends(require_roles(*CONSOLE_READ_ROLES))])
    def diff(
        name: str = Query(max_length=120),
        from_version: int = Query(alias="from", ge=1),
        to_version: int = Query(alias="to", ge=1),
        db: Session = Depends(get_db),
    ):
        return {"diff": diff_versions(db, model, name, from_version, to_version)}

    @router.post("/rollback", dependencies=[Depends(require_roles(*CONSOLE_WRITE_ROLES))])
    def rollback(
        request: Request,
        payload: RollbackRequest,
        db: Session = Depends(get_db),
        principal: Principal = Depends(get_principal),
    ):
        _require_global(principal)
        row = rollback_to_version(
            db, model, payload.name, payload.version,
            created_by=request.state.user.id,
            now=request.app.state.clock.now(),
        )
        record_audit_from_request(
            request, db, action=f"{kind}.rollback", object_type=kind,
            object_id=row.id,
            after={"name": row.name, "republished_from": payload.version,
                   "new_version": row.version},
        )
        return {"item": _view_single(db, row)}

    return router


prompts_router = _build_router(
    "prompts", Prompt, _prompt_view, PromptCreateRequest, PromptContentUpdateRequest
)
policies_router = _build_router(
    "policies", Policy, _policy_view, PolicyCreateRequest, PolicyContentUpdateRequest
)
