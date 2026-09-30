"""Versioned-content lifecycle shared by prompts and policies (spec §17)."""

from __future__ import annotations

import difflib
import json
import time
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES, is_insert_race, write_conflict_backoff
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


class _Unset:
    """「안 보냈다」와 「빈 값을 보냈다」는 서로 다른 사실이라 값 하나로는 담을 수 없다.

    `app/users/service.py::UNSET` 과 `app/knowledge/schemas.py` 의 `model_fields_set` 규약이
    같은 문제를 같은 모양으로 푼다 — 안 보낸 칸을 기본값으로 채우면 그 기본값이 저장된 값을
    덮어쓴다.
    """

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 표시용
        return "UNSET"


UNSET = _Unset()


def update_draft(
    db: Session,
    row: VersionedModel,
    *,
    content: str | _Unset = UNSET,
    purpose: str | None | _Unset = UNSET,
    slot: str | None | _Unset = UNSET,
) -> VersionedModel:
    """초안에서 **보낸 칸만** 고친다.

    왜 「보낸 칸만」인가: 관리자 콘솔(DataScreen)은 바뀐 필드만 PATCH 로 보낸다. 예전에는 이
    자리에서 `content` 를 무조건 덮어썼는데, 정책 요청 스키마의 `content` 기본값이 `"{}"` 라
    「용도」 한 줄만 고쳐도 그 정책의 규칙 전체가 빈 객체로 지워지고 응답은 200 이었다.
    같은 요청을 프롬프트에 보내면 `content` 가 필수라 422 로 막혀, 쌍둥이 화면의 답이 서로
    달랐다. PATCH 는 보낸 것만 바꾼다 — 안 보낸 칸은 저장된 값을 그대로 둔다.

    상태 게이트는 예전 `update_content` 와 같다. 발행 이력이 남는 자원이라 **초안에서만**
    고친다. 그래야 이미 발행된 버전의 내용과 용도가 버전 기록 없이 바뀌는 일이 없다.
    """
    if row.status != STATUS_DRAFT:
        raise ConflictError("draft 상태에서만 내용을 수정할 수 있습니다.")
    if not isinstance(content, _Unset):
        _set_content(row, content)
    if not isinstance(purpose, _Unset):
        row.purpose = purpose
    if not isinstance(slot, _Unset) and isinstance(row, Prompt):
        row.slot = slot or None
    db.flush()
    return row


def _published_to_replace(db: Session, row: VersionedModel) -> list[VersionedModel]:
    """이 행을 발행하면 내려가야 하는 발행본들. 이름마다 하나, 그리고 프롬프트는 사용처마다 하나다(D-518)."""
    model = type(row)
    found = {}
    current = get_published(db, model, row.name)
    if current is not None and current.id != row.id:
        found[current.id] = current
    if isinstance(row, Prompt) and row.slot:
        for other in db.execute(
            select(Prompt).where(Prompt.slot == row.slot, Prompt.status == STATUS_PUBLISHED, Prompt.id != row.id)
        ).scalars():
            found[other.id] = other
    return list(found.values())


def transition(
    db: Session, row: VersionedModel, new_status: str, *, now: datetime
) -> VersionedModel:
    allowed = VALID_TRANSITIONS.get(row.status)
    if allowed is None or new_status not in allowed:
        raise ConflictError(f"{row.status} → {new_status} 전환은 허용되지 않습니다.")
    if new_status == STATUS_PUBLISHED and isinstance(row, Prompt):
        # 발행은 「이 사용처에서 다음 호출부터 쓴다」는 뜻이다. 사용처와 지시문을 여기서 본다(D-518).
        from app.ai.prompts.service import validate_for_publish

        validate_for_publish(row.slot, row.content)
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
                # 이름마다, 그리고 프롬프트는 사용처마다 발행본이 하나다 — 앞의 것은 보관하고 덮어쓰지 않는다
                # (spec §17.1, D-518).
                replaced = _published_to_replace(db, row)
                for current in replaced:
                    current.status = STATUS_ARCHIVED
                if replaced:
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
        if not is_insert_race(exc):
            raise
        raise ConflictError(
            "다른 버전이 거의 동시에 발행돼 충돌했습니다. 최신 상태를 다시 불러오세요."
        ) from None
    return row


_NEW_VERSION_RETRIES = DEFAULT_WRITE_CONFLICT_RETRIES


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
    # Policy.purpose, 마이그레이션 0058) 새 버전에도 그대로 이어간다. 러너 참조는
    # 여전히 Prompt 전용이다.
    purpose = row.purpose
    slot = row.slot if is_prompt else None
    source_content = content if content is not None else _model_content(row)
    # UB-21: 같은 이름에 "새 버전" 요청 두 개가 거의 동시에 오면(연타·재제출) 둘 다 같은
    # next_version()을 읽어 같은 버전 번호로 삽입을 시도할 수 있다 - uq_{prompts,policies}
    # _name_version 유일 제약이 진 쪽을 IntegrityError로 막는데, 여태 아무도 안 잡아서
    # 그대로 500으로 샜다. approvals.create_approval과 같은 관용: SAVEPOINT 안에서
    # 시도하고, 지면 커밋(스냅샷을 새로 뜬다 - CORE-13, "낡은 스냅샷은 SAVEPOINT
    # 롤백으로도 안 새로고침된다")한 뒤 버전 번호를 다시 계산해 재시도한다. router.py의
    # create()와 달리 이건 재시도만으로 실제로 풀리는 경합이라(다음 루프의 next_version()
    # 이 다른 번호를 준다) 사용자에게 409를 보여줄 이유가 없다 — **재시도가 성공하는 한**
    # 그렇다는 뜻이다. PA-RC-0008: 예산(예전엔 5, 지터 없음)을 소진하면 이 이유가 더는
    # 성립하지 않는데도 raw OperationalError/IntegrityError를 그대로 올려 500이 났다
    # (8-way 경합 실측 약 40%). auth/router.py 로그인 재시도의 실측값(10회+지터)으로
    # 예산을 올리고, 소진 시에는 사용자에게 뜻이 통하는 409로 바꾼다.
    for attempt in range(_NEW_VERSION_RETRIES):
        version = next_version(db, model, name)
        if is_prompt:
            copy = Prompt(
                name=name,
                purpose=purpose,
                version=version,
                content=source_content,
                slot=slot,
                status=STATUS_DRAFT,
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
            if not is_insert_race(exc):
                raise
            if attempt == _NEW_VERSION_RETRIES - 1:
                raise ConflictError(
                    "다른 새 버전 요청과 계속 겹쳐 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."
                ) from None
            # 스냅샷을 새로 뜨는 이 commit 자체도 경합에서 같은 이유로 거부될 수 있다
            # (org/service.py::create_item과 같은 자리, D-75/PA-08과 같은 패턴) —
            # 처리 안 하면 예산이 남았는데도 raw OperationalError가 새 나간다.
            try:
                db.commit()
            except (IntegrityError, OperationalError) as commit_exc:
                if not is_insert_race(commit_exc):
                    raise
                db.rollback()
            time.sleep(write_conflict_backoff(attempt))
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
    """옛 버전의 내용을 **새 버전으로** 다시 발행한다. 되돌리기는 관리자가 명시한 동작이라 초안에서 곧바로 발행한다."""
    source = get_version_row(db, model, name, version)
    copy = new_version_from(db, source, created_by=created_by)
    transition(db, copy, STATUS_PUBLISHED, now=now)
    return copy


def validate_policy_content(content: str) -> None:
    import json

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValidationAppError(f"Policy 내용이 올바른 JSON이 아닙니다: {exc}") from None
    if not isinstance(parsed, dict):
        raise ValidationAppError("Policy 내용은 JSON 객체여야 합니다.")
