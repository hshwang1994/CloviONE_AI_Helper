"""문서의 판 — 쌓고 · 비교하고 · 되돌린다 (S7 Exit).

## 판을 만드는 자리는 여기 하나다

`DocumentVersion(...)` 을 만드는 코드가 두 곳이 되면 한쪽이 `version_no` 를 다르게
매기거나 파생을 안 만들고, 그 문서는 이력이 끊긴 채로 남는다. 끊긴 이력은 되돌릴 수
없고 다시 계산해서 복구할 수도 없다 — 그때의 본문이 어디에도 없기 때문이다.
`scripts/check_domain_single_source.py` 가 이 규칙을 코드로 확인한다.

## 되돌리기는 지우는 것이 아니라 쌓는 것이다

3판에서 1판으로 되돌리면 1판과 같은 본문의 **4판**이 생긴다. 이력을 잘라 내면
「누가 언제 무엇을 되돌렸는가」가 사라지고, 그 질문은 사고가 난 다음에만 나온다.
그래서 `source = 'RESTORE'` 와 `change_reason` 을 함께 남긴다.

## 같은 본문을 다시 저장하면 판을 안 만든다

편집기는 커서만 움직여도 저장을 부른다. 그때마다 판이 쌓이면 이력 화면이 「변경 없음」
수백 줄이 되고, 그 안에서 실제 변경을 못 찾는다. 정본(Block JSON)이 같으면 판을
만들지 않는다 — **파생이 아니라 정본으로 비교한다**(파생은 같은 정본에서 늘 같다).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.knowledge import blocks
from app.knowledge.models import (
    VSRC_RESTORE,
    VSRC_USER,
    Document,
    DocumentVersion,
)

__all__ = ["snapshot", "history", "get", "current", "restore", "compare"]

logger = logging.getLogger("app.knowledge.versions")


def snapshot(
    db: Session,
    document: Document,
    body: Any,
    *,
    author_id: str | None,
    change_reason: str | None = None,
    ai_used: bool = False,
    source: str = VSRC_USER,
    reindex: bool = True,
) -> DocumentVersion | None:
    """새 판을 쌓고 `current_version_id` 를 옮긴다. 내용이 같으면 `None`.

    파생 셋(`body`·`body_markdown`·`body_text`)을 `blocks.derive()` 하나가 함께 만든다 —
    이 함수가 그 결과를 나눠 담는 유일한 자리다.

    `reindex=False` 는 **이관 전용**이다 (S13). 적재 직후 `ai_index_state` 는 비어 있는
    것이 정상이고(D-270), 상태 행이 없는 문서는 색인 레인의 훑기가 스스로 찾아 돈다
    (S9). 여기서 110건을 미리 넣으면 훑기가 할 일을 두 번 하는 것이고, 무엇보다
    「적재 직후 파생 넷은 비어 있다」는 이관 검증의 불변식이 깨진다.
    """
    previous = current(db, document)
    try:
        # 앞판을 함께 넘긴다 — id 를 안 돌려주는 클라이언트의 앵커가 여기서 이어진다
        # (`blocks.normalize` 의 `carry_from`). 우리 편집기는 이 경로를 안 탄다.
        derived = blocks.derive(body, carry_from=previous.body if previous else None)
    except blocks.BlockError as exc:
        # 본문의 모양이 틀린 것은 **사용자 입력 오류**다. 그대로 올리면 `ValueError` 라
        # 500 이 되고, 화면에는 「알 수 없는 오류」만 뜬다 — 무엇을 고쳐야 하는지 못 본다.
        raise ValidationAppError(str(exc)) from exc

    if previous is not None and previous.body == derived.body:
        return None

    version = DocumentVersion(
        id=str(uuid.uuid4()),
        document_id=document.id,
        version_no=(previous.version_no + 1) if previous else 1,
        body=derived.body,
        body_markdown=derived.markdown,
        body_text=derived.text,
        author_id=author_id,
        change_reason=(change_reason or "").strip() or None,
        ai_used=ai_used,
        source=source,
        prev_version_id=previous.id if previous else None,
    )
    db.add(version)
    db.flush()
    document.current_version_id = version.id
    db.flush()
    if reindex:
        _reindex(db, document.id)
    return version


def _reindex(db: Session, document_id: str) -> None:
    """본문이 바뀌었으니 이 문서를 다시 색인해야 한다고 적는다 (S9 · D-203).

    이 자리에 두는 이유: `current_version_id` 를 옮기는 곳이 이 함수 하나다. 라우터마다
    신호를 걸면 새 저장 경로가 하나 생길 때 그것만 신호를 빠뜨리고, 그 문서는 **영원히**
    옛 내용으로 검색된다. 훑기(`sweep_stale`)가 결국 잡지만 그것은 안전망이지 설계가
    아니다.

    같은 트랜잭션이라 「저장은 됐는데 색인 신호는 안 갔다」가 안 생긴다. 그리고 색인이
    본문 저장을 막지도 않는다 — 여기서 실패해도 훑기가 같은 일을 한다.

    import 를 함수 안에서 하는 이유는 순환이다: 색인 쪽이 `app/knowledge/models.py` 와
    `app/knowledge/blocks.py` 를 읽는다.
    """
    from app.ai.index import service as index_service

    try:
        # SAVEPOINT 로 감싸는 것이 요점이다. 그냥 잡기만 하면 실패한 flush 가 바깥
        # 트랜잭션을 이미 망가뜨린 뒤라, 「저장을 안 막는다」가 말뿐이 된다.
        with db.begin_nested():
            index_service.enqueue(db, document_id)
    except Exception:  # noqa: BLE001 - 색인 신호 하나 때문에 본문 저장이 실패하지 않는다
        logger.exception("색인 신호를 남기지 못했다 document_id=%s", document_id)


def current(db: Session, document: Document) -> DocumentVersion | None:
    """지금 보여 주는 판.

    `current_version_id` 를 먼저 본다. 그것이 비어 있는 문서(아직 본문을 한 번도 안 쓴
    문서)에서만 가장 높은 번호로 떨어진다 — 순서를 반대로 하면 되돌리기 직후에
    「가장 높은 번호」와 「지금 판」이 달라서 옛 본문을 보여 준다.
    """
    if document.current_version_id:
        row = db.get(DocumentVersion, document.current_version_id)
        if row is not None:
            return row
    return db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_no.desc())
        .limit(1)
    ).scalars().first()


def history(db: Session, document: Document, *, limit: int = 50) -> list[DocumentVersion]:
    """최신 판부터. 본문은 실어 보내지 않는다 — 목록 한 화면이 수십 판의 본문을
    통째로 나르면 그 화면만으로 응답이 메가바이트가 된다. 본문은 `get()` 이 준다."""
    return list(
        db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_no.desc())
            .limit(limit)
        ).scalars().all()
    )


def get(db: Session, document: Document, version_no: int) -> DocumentVersion:
    row = db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.version_no == version_no,
        )
    ).scalars().first()
    if row is None:
        raise NotFoundError("그 판을 찾지 못했습니다.")
    return row


def compare(
    db: Session, document: Document, *, base_no: int, target_no: int
) -> dict[str, Any]:
    """두 판의 차이. 블록 단위다 (D-198).

    같은 판을 두 번 주면 빈 차이를 낸다 — 거절하지 않는다. 화면이 목록에서 같은 줄을
    두 번 고르는 것은 실수이지 오류가 아니고, 빈 결과가 그 사실을 그대로 보여 준다.
    """
    base = get(db, document, base_no)
    target = get(db, document, target_no)
    return {
        "base": {"version_no": base.version_no, "created_at": base.created_at},
        "target": {"version_no": target.version_no, "created_at": target.created_at},
        "changes": blocks.diff(base.body, target.body),
    }


def restore(
    db: Session,
    document: Document,
    version_no: int,
    *,
    author_id: str | None,
    expected_version: int | None = None,
) -> DocumentVersion:
    """옛 판의 본문으로 **새 판을 쌓는다**. 이력은 그대로 남는다.

    `expected_version` 은 문서의 낙관적 잠금 값이다(D-240). 되돌리기는 남의 편집을
    통째로 덮는 동작이라, 「내가 이력을 본 뒤 누군가 저장했다」를 반드시 잡아야 한다 —
    안 잡으면 방금 쓴 문단이 조용히 사라지고 사라진 사람은 그 사실을 모른다.
    """
    if expected_version is not None and document.version != expected_version:
        raise ConflictError("다른 사람이 먼저 저장했습니다. 새로 고친 뒤 다시 시도해 주세요.")

    source_version = get(db, document, version_no)
    now_showing = current(db, document)
    if now_showing is not None and now_showing.version_no == version_no:
        raise ConflictError("이미 그 판을 보고 있습니다.")

    version = snapshot(
        db,
        document,
        source_version.body,
        author_id=author_id,
        change_reason=f"{version_no}판으로 되돌림",
        ai_used=False,
        source=VSRC_RESTORE,
    )
    if version is None:
        # `snapshot` 은 정본이 같으면 `None` 을 낸다. 위에서 「지금 그 판」을 이미
        # 걸렀으므로, 여기 오는 것은 **번호가 다른데 본문이 같은** 판이다(예: 3판이
        # 1판을 되돌린 것이고 지금 다시 1판을 고른 경우). 되돌릴 것이 없다.
        raise ConflictError("그 판은 지금 본문과 내용이 같습니다.")
    document.version += 1
    db.flush()
    return version
