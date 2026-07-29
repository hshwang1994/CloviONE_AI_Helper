"""Versioned-content lifecycle shared by prompts and policies (spec §17)."""

from __future__ import annotations

import difflib
import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
    if new_status == STATUS_PUBLISHED:
        # Only one published version per name — the previous one is archived,
        # never overwritten (spec §17.1).
        current = get_published(db, type(row), row.name)
        if current is not None and current.id != row.id:
            current.status = STATUS_ARCHIVED
        row.published_at = now
    row.status = new_status
    db.flush()
    return row


def new_version_from(
    db: Session,
    row: VersionedModel,
    *,
    content: str | None = None,
    created_by: str | None,
) -> VersionedModel:
    model = type(row)
    version = next_version(db, model, row.name)
    if isinstance(row, Prompt):
        copy = Prompt(
            name=row.name,
            purpose=row.purpose,
            version=version,
            content=content if content is not None else row.content,
            status=STATUS_DRAFT,
            runner_id=row.runner_id,
            created_by=created_by,
        )
    else:
        copy = Policy(
            name=row.name,
            version=version,
            content_json=content if content is not None else row.content_json,
            status=STATUS_DRAFT,
            created_by=created_by,
        )
    db.add(copy)
    db.flush()
    return copy


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
