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
    "list_for_org", "usage_counts", "get_or_404", "rename", "remove",
    "TAG_MAX_PER_DOCUMENT", "TAG_NAME_MAX",
]

#: 태그 이름의 상한. 컬럼과 같은 값이다 — 여기서 안 막으면 DB 가 500 으로 막는다.
TAG_NAME_MAX = 80

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


# ── 태그를 사람이 관리한다 (지시 22-5) ──────────────────────────────────────
#
# 지금까지 태그는 **문서를 저장할 때 곁다리로** 생겼다(`ensure`). 그래서 오타로 만든
# 태그를 고칠 방법이 없었고, 안 쓰는 태그를 치울 방법도 없었다 — 목록은 늘기만 했다.
#
# 이름을 고치면 **slug 도 함께** 고친다. slug 는 비교에 쓰는 형태라, 이름만 바꾸면
# 다음 사람이 새 이름을 적었을 때 옛 slug 를 못 찾아 **같은 뜻의 태그가 하나 더** 생긴다.


def _org_clause(org_id: str | None):
    return Tag.org_id.is_(None) if org_id is None else Tag.org_id == org_id


def list_for_org(db: Session, org_id: str | None) -> list[Tag]:
    return list(db.execute(
        select(Tag).where(_org_clause(org_id)).order_by(Tag.slug)
    ).scalars().all())


def usage_counts(db: Session, tag_ids: list[str], *, document_ids=None) -> dict[str, int]:
    """{tag_id: 붙어 있는 문서 수}.

    `document_ids` 를 주면 **그 집합 안에서만** 센다. 부르는 쪽이 「내가 볼 수 있는 문서」를
    넘기므로, 남의 부서 문서에만 붙은 태그가 「3건 사용 중」으로 보이지 않는다 — 수 하나도
    그 공간에 무엇이 있는지 말해 준다.
    """
    from sqlalchemy import func

    if not tag_ids:
        return {}
    stmt = (
        select(DocumentTag.tag_id, func.count())
        .where(DocumentTag.tag_id.in_(tuple(tag_ids)))
        .group_by(DocumentTag.tag_id)
    )
    if document_ids is not None:
        if not document_ids:
            return {}
        stmt = stmt.where(DocumentTag.document_id.in_(tuple(document_ids)))
    return {tag_id: int(n) for tag_id, n in db.execute(stmt).all()}


def get_or_404(db: Session, org_id: str | None, tag_id: str) -> Tag:
    """이 조직의 태그 하나. 다른 조직 것이면 **없는 것**이다(404).

    403 은 「그 조직에 그런 태그가 있다」를 알려 준다.
    """
    from app.core.errors import NotFoundError

    tag = db.get(Tag, tag_id)
    if tag is None or tag.org_id != org_id:
        raise NotFoundError("태그를 찾지 못했습니다.")
    return tag


def _clean_name(name: str) -> tuple[str, str]:
    clean = (name or "").strip()
    if not clean:
        raise ValidationAppError("태그 이름을 입력해 주세요.")
    if len(clean) > TAG_NAME_MAX:
        raise ValidationAppError(f"태그 이름은 {TAG_NAME_MAX}자 이하여야 합니다.")
    slug = slugify(clean)
    if not slug:
        raise ValidationAppError("태그 이름을 입력해 주세요.")
    return clean, slug


def create(db: Session, org_id: str | None, name: str) -> Tag:
    """새 태그. 같은 뜻의 태그가 이미 있으면 **거절한다.**

    `ensure` 와 다른 점이 그것이다: 문서를 저장하다 만들어지는 쪽은 있으면 그것을 쓰는 것이
    맞고(사용자는 태그를 만들려던 것이 아니다), 관리 화면에서 「추가」를 누른 사람에게는
    「이미 있습니다」가 정확한 답이다.
    """
    from app.core.errors import ConflictError

    clean, slug = _clean_name(name)
    found = db.execute(
        select(Tag).where(Tag.slug == slug, _org_clause(org_id))
    ).scalars().first()
    if found is not None:
        raise ConflictError(f"같은 이름의 태그가 이미 있습니다: {found.name}")
    tag = Tag(org_id=org_id, name=clean, slug=slug)
    db.add(tag)
    db.flush()
    return tag


def rename(db: Session, tag: Tag, name: str) -> Tag:
    """이름과 slug 를 함께 고친다. 다른 태그와 겹치면 거절한다.

    합치기(merge)는 안 한다 — 두 태그를 하나로 합치는 것은 문서 여럿의 분류를 바꾸는
    일이고, 이름을 고치다 실수로 그 일이 일어나면 되돌릴 방법이 없다.
    """
    from app.core.errors import ConflictError

    clean, slug = _clean_name(name)
    if slug != tag.slug:
        clash = db.execute(
            select(Tag).where(Tag.slug == slug, _org_clause(tag.org_id), Tag.id != tag.id)
        ).scalars().first()
        if clash is not None:
            raise ConflictError(f"같은 이름의 태그가 이미 있습니다: {clash.name}")
    tag.name = clean
    tag.slug = slug
    db.flush()
    return tag


def remove(db: Session, tag: Tag) -> int:
    """태그를 지운다. **문서는 안 지운다** — 연결만 끊긴다.

    `document_tags.tag_id` 가 `ON DELETE CASCADE` 라 연결 행은 DB 가 정리한다. 고아 행이
    남지 않는 것이 여기서 확인해야 하는 사실이고, 지운 연결 수를 돌려줘 화면이 「문서 3건에서
    뗐습니다」라고 말할 수 있게 한다.
    """
    used = len(db.execute(
        select(DocumentTag.document_id).where(DocumentTag.tag_id == tag.id)
    ).scalars().all())
    db.delete(tag)
    db.flush()
    return used


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
