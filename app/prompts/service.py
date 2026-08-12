"""Versioned-content lifecycle shared by prompts and policies (spec §17)."""

from __future__ import annotations

import difflib
import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import is_write_conflict
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.prompts.models import (
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    VALID_TRANSITIONS,
    Policy,
    Prompt,
)

VersionedModel = Prompt | Policy


def _model_content(row: VersionedModel) -> str:
    return row.content if isinstance(row, Prompt) else row.content_json


def _set_content(row: VersionedModel, content: str) -> None:
    if isinstance(row, Prompt):
        row.content = content
    else:
        row.content_json = content


def get_or_404(db: Session, model: type[VersionedModel], row_id: str) -> VersionedModel:
    row = db.get(model, row_id)
    if row is None:
        raise NotFoundError("대상 버전을 찾을 수 없습니다.")
    return row


def next_version(db: Session, model: type[VersionedModel], name: str) -> int:
    current = db.execute(
        select(func.max(model.version)).where(model.name == name)
    ).scalar_one()
    return (current or 0) + 1


def get_version_row(
    db: Session, model: type[VersionedModel], name: str, version: int
) -> VersionedModel:
    row = db.execute(
        select(model).where(model.name == name, model.version == version)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"'{name}' 버전 {version}을 찾을 수 없습니다.")
    return row


def get_published(
    db: Session, model: type[VersionedModel], name: str
) -> VersionedModel | None:
    return db.execute(
        select(model).where(model.name == name, model.status == STATUS_PUBLISHED)
    ).scalar_one_or_none()


def update_content(db: Session, row: VersionedModel, content: str) -> VersionedModel:
    if row.status != STATUS_DRAFT:
        raise ConflictError("draft 상태에서만 내용을 수정할 수 있습니다.")
    _set_content(row, content)
    db.flush()
    return row


def transition(
    db: Session, row: VersionedModel, new_status: str, *, now: datetime
) -> VersionedModel:
    allowed = VALID_TRANSITIONS.get(row.status)
    if allowed is None or new_status not in allowed:
        raise ConflictError(f"{row.status} → {new_status} 전환은 허용되지 않습니다.")
    # UB-04: 이 읽기~쓰기 사이는 잠기지 않는다(커밋은 요청 끝에 한 번). 두 관리자가 같은
    # 이름의 서로 다른 버전을 거의 동시에 발행하면 둘 다 "기존 발행본 없음/다름"을 보고
    # 각자 자기 행을 published로 만들 수 있다 — 그러면 이후 그 이름의 모든 조회가
    # `MultipleResultsFound` → 500이 된다. DB의 부분 유일 인덱스(migration 0053,
    # `ux_{prompts,policies}_published_dedup`)가 경합의 승자를 하나로 정해 주므로,
    # 진 쪽은 `IntegrityError`를 받고 깨끗한 409로 알린다 — approvals의 0052와 같은 패턴.
    # (예전엔 archived로 내리는 UPDATE만 SAVEPOINT 밖에 있어 그 문장에서 난 경합이
    # 잡히지 않은 채 500으로 샜다 — 두 UPDATE를 하나의 SAVEPOINT로 함께 묶는다.)
    try:
        with db.begin_nested():
            if new_status == STATUS_PUBLISHED:
                # Only one published version per name — the previous one is
                # archived, never overwritten (spec §17.1).
                current = get_published(db, type(row), row.name)
                if current is not None and current.id != row.id:
                    current.status = STATUS_ARCHIVED
                    # 이 행을 먼저(별도로) 내보낸다 — 옛 발행본을 archived로 내리는
                    # UPDATE와 새 행을 published로 올리는 UPDATE가 **같은 flush**에
                    # 섞이면, SQLAlchemy가 두 문장을 내보내는 순서에 따라 "새 행
                    # published" 쪽이 먼저 실행될 수 있고, 그 순간 아직 archived가 안
                    # 된 옛 발행본과 함께 **같은 이름에 published가 둘**인 상태가
                    # 찰나라도 생겨 부분 유일 인덱스(아래)가 우리 자신의 정상 경로를
                    # 오탐으로 막는다(`test_publish_archives_previous_published`가
                    # 실제로 이렇게 깨졌다 — 고치면서 재현·확인함). 옛 발행본을 먼저
                    # 내려 그 겹침 자체를 없앤다.
                    db.flush()
                row.published_at = now
            row.status = new_status
            db.flush()
    except (IntegrityError, OperationalError) as exc:
        if not is_write_conflict(exc):
            raise
        raise ConflictError(
            "다른 버전이 거의 동시에 발행돼 충돌했습니다. 최신 상태를 다시 불러오세요."
        ) from None
    return row


_NEW_VERSION_RETRIES = 5


def new_version_from(
    db: Session,
    row: VersionedModel,
    *,
    content: str | None = None,
    created_by: str | None,
) -> VersionedModel:
    model = type(row)
    name = row.name
    is_prompt = isinstance(row, Prompt)
    # WF1 단독 결함 — purpose는 이제 Prompt/Policy 둘 다 있어(app/prompts/models.py::
    # Policy.purpose, 마이그레이션 0058) 새 버전에도 그대로 이어간다. runner_id는
    # 여전히 Prompt 전용이다.
    purpose = row.purpose
    runner_id = row.runner_id if is_prompt else None
    source_content = content if content is not None else _model_content(row)
    # UB-21: 같은 이름에 "새 버전" 요청 두 개가 거의 동시에 오면(연타·재제출) 둘 다 같은
    # next_version()을 읽어 같은 버전 번호로 삽입을 시도할 수 있다 - uq_{prompts,policies}
    # _name_version 유일 제약이 진 쪽을 IntegrityError로 막는데, 여태 아무도 안 잡아서
    # 그대로 500으로 샜다. approvals.create_approval과 같은 관용: SAVEPOINT 안에서
    # 시도하고, 지면 커밋(스냅샷을 새로 뜬다 - CORE-13, "낡은 스냅샷은 SAVEPOINT
    # 롤백으로도 안 새로고침된다")한 뒤 버전 번호를 다시 계산해 재시도한다. router.py의
    # create()와 달리 이건 재시도만으로 실제로 풀리는 경합이라(다음 루프의 next_version()
    # 이 다른 번호를 준다) 사용자에게 409를 보여줄 이유가 없다.
    for attempt in range(_NEW_VERSION_RETRIES):
        version = next_version(db, model, name)
        if is_prompt:
            copy = Prompt(
                name=name,
                purpose=purpose,
                version=version,
                content=source_content,
                status=STATUS_DRAFT,
                runner_id=runner_id,
                created_by=created_by,
            )
        else:
            copy = Policy(
                name=name,
                purpose=purpose,
                version=version,
                content_json=source_content,
                status=STATUS_DRAFT,
                created_by=created_by,
            )
        try:
            with db.begin_nested():
                db.add(copy)
                db.flush()
            return copy
        except (IntegrityError, OperationalError) as exc:
            if not is_write_conflict(exc) or attempt == _NEW_VERSION_RETRIES - 1:
                raise
            db.commit()
    raise AssertionError("unreachable")  # pragma: no cover


def _diff_lines(row: VersionedModel) -> list[str]:
    """diff에 넣을 줄 목록. Policy는 한 줄 minified JSON으로 저장되므로, 그대로
    line-diff하면 아무리 작은 변경도 '전체 줄 삭제 + 전체 줄 추가'로 나와 어떤 필드가
    바뀌었는지 알 수 없다. Policy일 때만 보기 좋게 편집(indent+정렬)한 뒤 줄로 쪼갠다.
    Prompt는 자유 다중행 텍스트라 그대로 둔다."""
    content = _model_content(row)
    if isinstance(row, Policy):
        try:
            content = json.dumps(
                json.loads(content), indent=2, sort_keys=True, ensure_ascii=False
            )
        except (ValueError, TypeError):
            # 파싱 불가한 내용은 원문 그대로 비교한다(정보 손실 방지).
            pass
    return content.splitlines()


def diff_versions(
    db: Session, model: type[VersionedModel], name: str, from_version: int, to_version: int
) -> str:
    old = get_version_row(db, model, name, from_version)
    new = get_version_row(db, model, name, to_version)
    return "\n".join(
        difflib.unified_diff(
            _diff_lines(old),
            _diff_lines(new),
            fromfile=f"{name} v{from_version}",
            tofile=f"{name} v{to_version}",
            lineterm="",
        )
    )


def rollback_to_version(
    db: Session,
    model: type[VersionedModel],
    name: str,
    version: int,
    *,
    created_by: str | None,
    now: datetime,
) -> VersionedModel:
    """Republish an old version's content as a NEW published version."""
    source = get_version_row(db, model, name, version)
    copy = new_version_from(db, source, created_by=created_by)
    # Fast-track through the lifecycle — rollback is an explicit admin action.
    for step in ("test", "review", "published"):
        transition(db, copy, step, now=now)
    return copy


def validate_policy_content(content: str) -> None:
    import json

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationAppError(f"Policy 내용이 올바른 JSON이 아닙니다: {exc}") from None
    if not isinstance(parsed, dict):
        raise ValidationAppError("Policy 내용은 JSON 객체여야 합니다.")
