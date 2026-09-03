"""새 문서의 **출발점** (지시 22.5 · 문서 개편 7번).

## 왜 서버가 들고 있는가

본문의 정본은 ProseMirror Block Tree 다(D-198). 화면이 그 JSON 을 손으로 적으면 서버의
스키마(`blocks.BLOCK_NODES`)와 두 벌이 되고, 어긋난 쪽은 저장할 때가 아니라 **문서를 열
때** 빈 화면으로 드러난다. 그래서 틀은 여기서 만들고 화면은 이름만 고른다.

## 표가 생겼다 — 그리고 「빈 문서」만 표 밖에 남았다

예전에는 넷 다 모듈 상수였다. 「복잡한 관리 시스템은 필요할 때만」이라는 이유였는데,
그 필요가 왔다: 어휘를 하나 늘리려면 배포를 해야 했다. 분류와 태그는 이미 조직이 스스로
만드는데 틀만 코드에 얼어 있었다.

그런데 **「빈 문서」는 어휘가 아니라 화면의 바탕**이다. 표에 넣으면 지울 수 있게 되고,
지워진 날 새 문서 대화상자의 기본값이 없는 틀을 가리킨다. 그래서 그 하나만 상수로 남는다.
`GET /api/knowledge/templates` 의 봉투도 그대로다 — 화면은 표가 생긴 것을 모른다.

## 고쳐도 지워도 이미 만든 문서는 안 바뀐다

`documents` 에 `template_id` 가 **없다**(`models.DocumentTemplate` 참고). 본문은 문서를
만드는 순간 복사되고 그 뒤 둘은 남남이다. 규칙이 코드가 아니라 스키마다.

## 쓸 때 정규화한다

`body` 는 사람이 만든 Block JSON 이고 편집기가 그대로 그린다. 검사하는 자리는
`blocks.normalize` 하나이고(문서 본문과 같은 함수다), 그것을 안 지나면 이 표가 저장
XSS 의 입구가 된다.

## 틀이 채우는 것은 **질문**이지 문장이 아니다

「1. 배경」 아래에 예시 문장을 넣어 두면 그 문장이 지워지지 않은 채 저장된 문서가 반드시
생긴다. 그래서 각 칸에는 제목과 **무엇을 적는 자리인지**만 둔다.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.knowledge import blocks
from app.knowledge.models import DocumentTemplate

__all__ = [
    "BLANK",
    "BLANK_ROW",
    "TEMPLATE_NAME_MAX",
    "TEMPLATE_HELP_MAX",
    "catalog",
    "body_for",
    "list_for_org",
    "get_or_404",
    "create",
    "update",
    "remove",
]

#: 아무것도 안 채우는 선택지. **표의 행이 아니다** — 위 「빈 문서」 절을 보라.
BLANK = "blank"
BLANK_ROW: dict[str, Any] = {
    "id": BLANK,
    "name": "빈 문서",
    "help": "아무것도 없는 상태에서 시작합니다.",
    "empty": True,
    "builtin": True,
}

TEMPLATE_NAME_MAX = 80
TEMPLATE_HELP_MAX = 500

#: 화면 순서. 이름순이 아니라 사람이 정한 순서다 — 자주 쓰는 틀이 위에 선다.
_SORT_STEP = 1024


def _clean_name(name: str) -> str:
    clean = (name or "").strip()
    if not clean:
        raise ValidationAppError("템플릿 이름을 입력해 주세요.")
    if len(clean) > TEMPLATE_NAME_MAX:
        raise ValidationAppError(f"템플릿 이름은 {TEMPLATE_NAME_MAX}자까지 쓸 수 있습니다.")
    return clean


def _clean_help(help_text: str | None) -> str:
    clean = (help_text or "").strip()
    if len(clean) > TEMPLATE_HELP_MAX:
        raise ValidationAppError(f"템플릿 설명은 {TEMPLATE_HELP_MAX}자까지 쓸 수 있습니다.")
    return clean


def _clean_body(body: dict | None) -> dict:
    """본문을 문서와 **같은 함수**로 정규화한다.

    여기서 검사를 건너뛰면 이 표가 저장 XSS 의 입구가 된다 — 틀의 본문은 새 문서의
    본문이 되고, 편집기는 그것을 그대로 그린다.
    """
    try:
        return blocks.normalize(body if body is not None else blocks.empty_doc())
    except blocks.BlockError as exc:
        # 본문의 모양이 틀린 것은 **사용자 입력 오류**다. 그대로 올리면 `ValueError` 라
        # 500 이 되고, 화면에는 「알 수 없는 오류」만 뜬다 (`versions.snapshot` 과 같은 처리).
        raise ValidationAppError(str(exc)) from exc


def list_for_org(db: Session, org_id: str | None) -> list[DocumentTemplate]:
    stmt = select(DocumentTemplate).where(
        DocumentTemplate.org_id.is_(None) if org_id is None else DocumentTemplate.org_id == org_id
    )
    return list(db.execute(
        stmt.order_by(DocumentTemplate.sort_order, DocumentTemplate.name)
    ).scalars().all())


def get_or_404(db: Session, org_id: str | None, template_id: str) -> DocumentTemplate:
    """범위 밖은 **404**. 남의 조직 틀의 존재를 id 하나로 확인할 수 없어야 한다."""
    row = db.get(DocumentTemplate, template_id)
    if row is None or row.org_id != org_id:
        raise NotFoundError("템플릿을 찾지 못했습니다.")
    return row


def json_of(row: DocumentTemplate, *, with_body: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "help": row.help or "",
        "empty": False,
        "builtin": False,
    }
    if with_body:
        out["body"] = copy.deepcopy(row.body)
    return out


def catalog(db: Session, org_id: str | None) -> list[dict[str, Any]]:
    """화면이 그리는 목록. **본문은 안 싣는다** — 고르는 자리에 필요한 것은 이름과 설명뿐이고,
    본문까지 실으면 문서를 만들지 않는 사람에게도 Block JSON 이 통째로 나간다.

    「빈 문서」가 언제나 맨 앞이다. 표가 비어도 고를 것이 하나는 있다.
    """
    return [dict(BLANK_ROW)] + [json_of(row) for row in list_for_org(db, org_id)]


def body_for(db: Session, org_id: str | None, template_id: str | None) -> dict[str, Any] | None:
    """틀 하나의 본문 **새 사전**.

    모르는 이름은 `None` — 거절하지 않는다. 틀을 하나 없앤 날 그 이름을 들고 온 요청이
    문서 생성 자체를 못 하게 되면, 사용자는 자기가 쓴 제목까지 잃는다. 빈 문서로 시작하는
    것은 잃는 것이 없다. 「이미 만든 문서는 안 바뀐다」와 같은 결의 판단이다.
    """
    if not template_id or template_id == BLANK:
        return None
    row = db.get(DocumentTemplate, template_id)
    if row is None or row.org_id != org_id or not row.body:
        return None
    # 표의 값을 그대로 주면 부르는 쪽이 그것을 고친다 — 그리고 그 수정이 **틀 자체**에
    # 남는다(`blocks.empty_doc` 과 같은 이유). 여기서 끊는다.
    return copy.deepcopy(row.body)


def _next_order(db: Session, org_id: str | None) -> int:
    rows = list_for_org(db, org_id)
    return (max((r.sort_order or 0) for r in rows) + _SORT_STEP) if rows else _SORT_STEP


def create(
    db: Session, *, org_id: str | None, name: str, help_text: str = "",
    body: dict | None = None, created_by: str | None = None,
) -> DocumentTemplate:
    clean = _clean_name(name)
    exists = db.execute(
        select(DocumentTemplate.id).where(
            DocumentTemplate.org_id.is_(None) if org_id is None else DocumentTemplate.org_id == org_id,
            DocumentTemplate.name == clean,
        )
    ).scalars().first()
    if exists:
        raise ConflictError("같은 이름의 템플릿이 이미 있습니다.")
    row = DocumentTemplate(
        org_id=org_id,
        name=clean,
        help=_clean_help(help_text),
        body=_clean_body(body),
        sort_order=_next_order(db, org_id),
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


#: `update` 의 「안 보냈다」 표식. `None` 은 「설명을 지운다」라 다른 값이 필요하다
#: (`service.save_document` 의 `UNSET` 과 같은 규약).
UNSET = object()


def update(
    db: Session, row: DocumentTemplate, *,
    name: str | None = None, help_text=UNSET, body=UNSET,
) -> DocumentTemplate:
    """틀 하나를 고친다. **이미 이 틀로 만든 문서는 안 바뀐다** — 참조가 없기 때문이다."""
    if name is not None:
        clean = _clean_name(name)
        if clean != row.name:
            exists = db.execute(
                select(DocumentTemplate.id).where(
                    DocumentTemplate.org_id.is_(None)
                    if row.org_id is None else DocumentTemplate.org_id == row.org_id,
                    DocumentTemplate.name == clean,
                    DocumentTemplate.id != row.id,
                )
            ).scalars().first()
            if exists:
                raise ConflictError("같은 이름의 템플릿이 이미 있습니다.")
            row.name = clean
    if help_text is not UNSET:
        row.help = _clean_help(help_text)
    if body is not UNSET:
        row.body = _clean_body(body)
    db.flush()
    return row


def remove(db: Session, row: DocumentTemplate) -> str:
    """틀을 지운다. **이 틀로 만든 문서는 그대로 남는다** — 참조가 없기 때문이다."""
    name = row.name
    db.delete(row)
    db.flush()
    return name
