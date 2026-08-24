"""태그 — 이름을 정규화해서 하나로 모은다 (S7).

## 왜 정규화가 필요한가

자유 문자열로 두면 「보안」·「보안 」·「 보안」·「보 안」이 서로 다른 태그가 된다.
사람은 그 넷을 같은 것으로 읽고, 태그로 거른 목록은 언제나 일부만 보여 준다 —
그리고 **빠진 것이 있다는 사실이 화면에 안 나온다.**

그래서 `slug`(정규화 형태)에 유일 제약을 걸고 `name` 은 처음 적은 표기를 그대로 둔다.
「Security」로 처음 만든 태그를 다음 사람이 「security」로 적어도 같은 태그가 되고,
화면에는 처음 표기가 보인다.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.knowledge.models import Document, DocumentTag, Tag

__all__ = [
    "slugify", "ensure", "set_for_document", "of_document", "of_documents",
    "TAG_MAX_PER_DOCUMENT",
]

# 한 문서에 붙는 태그 수 상한. 본문 길이는 안 막지만(D-198) 이것은 길이가 아니라
# **분류가 분류이기를 그만두는 지점**이다 — 50개가 붙은 문서는 어느 태그로도 안 좁혀진다.
TAG_MAX_PER_DOCUMENT = 20

_SPACE_RE = re.compile(r"\s+")


def slugify(name: str) -> str:
    """비교에 쓰는 형태. **한글을 로마자로 바꾸지 않는다.**

    `NFKC` 로 유니코드 표기를 통일하고(전각/반각·조합형/완성형), 공백을 하나로 접고,
    소문자로 내린다. 한글을 로마자로 바꾸는 라이브러리를 쓰면 「이」와 「리」가 같은
    slug 가 되는 식으로 **서로 다른 태그가 합쳐진다** — 갈라지는 것보다 나쁘다.
    """
    folded = unicodedata.normalize("NFKC", name or "").strip().casefold()
    return _SPACE_RE.sub(" ", folded)


def ensure(db: Session, org_id: str | None, name: str) -> Tag:
    """있으면 그것, 없으면 만든다.

    경합은 유일 제약이 잡는다 — 두 사람이 같은 태그를 동시에 처음 쓰면 한쪽이
    23505 를 받고, 부르는 쪽(`set_for_document`)이 다시 읽는다.
    """
    clean = (name or "").strip()
    if not clean:
        raise ValidationAppError("태그 이름을 입력해 주세요.")
    slug = slugify(clean)
    if not slug:
        raise ValidationAppError("태그 이름을 입력해 주세요.")

    stmt = select(Tag).where(Tag.slug == slug)
    stmt = stmt.where(Tag.org_id.is_(None) if org_id is None else Tag.org_id == org_id)
    found = db.execute(stmt).scalars().first()
    if found is not None:
        return found

    tag = Tag(org_id=org_id, name=clean, slug=slug)
    db.add(tag)
    db.flush()
    return tag


def set_for_document(db: Session, document: Document, names: list[str]) -> list[Tag]:
    """문서의 태그를 이 목록으로 **맞춘다**(늘리기가 아니다).

    화면이 태그 상자를 통째로 보내므로 여기서도 통째로 맞춘다. 차집합만 건드리는
    이유는 `mentions.sync` 와 같다 — 지웠다 다시 넣으면 `created_at` 이 저장할 때마다
    갱신돼 「언제부터 이 태그였나」가 사라진다.
    """
    wanted: dict[str, Tag] = {}
    for name in names or []:
        if not (name or "").strip():
            continue
        tag = ensure(db, document_org_id(db, document), name)
        wanted[tag.id] = tag
    if len(wanted) > TAG_MAX_PER_DOCUMENT:
        raise ValidationAppError(f"태그는 {TAG_MAX_PER_DOCUMENT}개까지 붙일 수 있습니다.")

    links = list(
        db.execute(
            select(DocumentTag).where(DocumentTag.document_id == document.id)
        ).scalars().all()
    )
    have = {link.tag_id for link in links}

    for link in links:
        if link.tag_id not in wanted:
            db.delete(link)
    for tag_id in wanted:
        if tag_id not in have:
            db.add(DocumentTag(document_id=document.id, tag_id=tag_id))
    db.flush()
    return sorted(wanted.values(), key=lambda t: t.slug)


def document_org_id(db: Session, document: Document) -> str | None:
    """문서가 속한 조직 — 공간이 든다. 문서는 소속 컬럼을 갖지 않는다(§5.3)."""
    from app.knowledge.models import KnowledgeSpace

    space = db.get(KnowledgeSpace, document.space_id)
    return space.org_id if space is not None else None


def of_document(db: Session, document_id: str) -> list[Tag]:
    return list(
        db.execute(
            select(Tag)
            .join(DocumentTag, DocumentTag.tag_id == Tag.id)
            .where(DocumentTag.document_id == document_id)
            .order_by(Tag.slug)
        ).scalars().all()
    )


def of_documents(db: Session, document_ids: list[str]) -> dict[str, list[Tag]]:
    """여러 문서의 태그를 한 질의로. 목록 화면이 문서 수만큼 묻지 않게 한다
    (`favorite_ids` 와 같은 이유 — `app/knowledge/service.py::favorite_ids`)."""
    if not document_ids:
        return {}
    rows = db.execute(
        select(DocumentTag.document_id, Tag)
        .join(Tag, Tag.id == DocumentTag.tag_id)
        .where(DocumentTag.document_id.in_(document_ids))
        .order_by(Tag.slug)
    ).all()
    out: dict[str, list[Tag]] = {}
    for document_id, tag in rows:
        out.setdefault(document_id, []).append(tag)
    return out
