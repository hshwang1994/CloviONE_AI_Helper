"""가져온 문서의 **프로젝트 · 분류 · 태그**를 제목과 본문으로 다시 정한다.

(문서 개편 11·12·15·16번)

## 왜 한 번에 판정해 버리지 않는가

원본이 이미 못 미덥다. Notion 문서 110건 중 프로젝트 관계가 있는 것은 **34건뿐**이고
(실측), Confluence 에는 그 축이 아예 없다. 그래서 이 판정은 규칙이 아니라 **추정**이다.
추정을 그 자리에서 DB 에 써 버리면 틀린 배정을 나중에 아무도 못 찾는다 — 「왜 이 문서가
저 프로젝트에 있나」에 답할 근거가 코드에만 남기 때문이다.

그래서 두 걸음으로 나눈다.

1. `propose()` 가 **사람이 읽고 고칠 수 있는 파일**(jsonl)을 만든다. 줄마다 판정과
   **근거**와 후보들이 함께 적힌다.
2. `apply()` 가 그 파일만 읽어 쓴다. 파일에 없는 문서는 안 건드린다.

## 🔴 판단이 안 서면 비운다

「가장 그럴듯한 것」을 억지로 고르지 않는다(11·15번). 후보가 둘 이상 비슷하면
`ambiguous` 이고, 근거가 없으면 `none` 이다. 둘 다 프로젝트를 안 붙인다 — 미지정으로
두는 것이 틀린 프로젝트에 넣는 것보다 언제나 낫다. 미지정 문서는 목록에서도 AI 검색에서도
빠지지 않으므로(문서 개편 4번) 잃는 것이 없다.

## 🔴 자체 작성 문서는 이 파일을 통해서도 안 바뀐다

적용기는 **로더와 같은 술어**를 다시 건다: `source_type='MIGRATION'` 이고 그 문서를
가리키는 `legacy_mapping` 행이 있을 것. 생성기가 어쩌다 자체 작성 문서의 id 를 뱉어도
(제목이 같거나 사람이 파일을 잘못 고쳤거나) 적용기가 거절한다. 보호를 한 자리에만 두면
그 자리를 안 지나는 경로가 언젠가 생긴다.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.knowledge import categories as doc_categories
from app.knowledge import service as knowledge_service
from app.knowledge import tags as doc_tags
from app.knowledge.models import (
    SOURCE_MIGRATION,
    Document,
    DocumentCategory,
    DocumentVersion,
    KnowledgeSpace,
    Tag,
)
from app.migration.models import T_DOCUMENT, LegacyMapping
from app.projects.models import Project

__all__ = [
    "DECISIONS",
    "Proposal",
    "propose",
    "write_proposals",
    "read_proposals",
    "apply",
    "is_rewritable",
]

#: 한 줄의 판정. 넷을 나누는 이유는 「못 정했다」가 두 가지 다른 사실이기 때문이다 —
#: 후보가 여럿이라 못 고른 것(`ambiguous`)과 근거가 아예 없는 것(`none`)은 사람이
#: 검토할 때 다른 행동을 부른다.
DECISION_MATCHED = "matched"
DECISION_AMBIGUOUS = "ambiguous"
DECISION_NONE = "none"
DECISION_MANUAL = "manual"   # 사람이 파일에서 직접 고쳤다
DECISIONS = (DECISION_MATCHED, DECISION_AMBIGUOUS, DECISION_NONE, DECISION_MANUAL)

#: 프로젝트로 인정할 최소 점수, 그리고 1등과 2등의 최소 차이.
#: 차이가 이보다 작으면 `ambiguous` 다 — 「거의 같은 후보 둘」에서 하나를 고르는 것은
#: 추정이 아니라 동전 던지기다.
#:
#: 🔴 점수만으로는 부족하다는 것을 실측이 보여 줬다. 아래 `_identity_tokens` 를 보라 —
#: **식별 낱말이 없으면 점수가 아무리 높아도 매칭하지 않는다.**
_MIN_SCORE = 4
_MIN_MARGIN = 3

#: 본문에서 볼 글자 수. 전문을 세면 긴 문서일수록 아무 프로젝트나 한 번씩 나온다.
_BODY_WINDOW = 4000

#: 이름에서 뽑을 수 없는 흔한 말. 이것들이 점수를 만들면 모든 문서가 같은 곳에 붙는다.
#:
#: 🔴 목록은 **실측으로 자랐다.** 첫 회차에서 `matched` 를 만든 낱말 상위 25개를 세어
#: 보니 `cloud`·`변경`·`데이터`·`클러스터`·`클라우드`·`기능`·`분석`·`인프라` 처럼 어느
#: 프로젝트도 안 가리키는 말이 대부분이었다. 다만 목록에 기대지 않는다 — 진짜 방어는
#: 아래 「식별 낱말」이고, 이 목록은 그 앞의 거친 체다.
_STOPWORDS = frozenset({
    "구축", "개발", "운영", "유지보수", "시스템", "포털", "포탈", "프로젝트", "고도화",
    "관리", "제품", "지원", "서비스", "플랫폼", "사업", "주식회사", "㈜",
    "cloud", "클라우드", "변경", "데이터", "클러스터", "기능", "분석", "인프라", "사내",
    "대비", "value", "pack", "개선", "정비", "환경", "설정", "정보", "작업", "가이드",
})

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def _norm(text: str | None) -> str:
    return unicodedata.normalize("NFKC", (text or "")).casefold()


def _tokens(text: str | None) -> list[str]:
    return [t for t in _TOKEN.findall(_norm(text)) if len(t) >= 2 and t not in _STOPWORDS]


@dataclass
class Proposal:
    """문서 하나에 대한 제안 한 줄."""

    document_id: str
    title: str
    source: str                     # notion | confluence
    decision: str = DECISION_NONE
    project_id: str | None = None
    project_name: str = ""
    evidence: str = ""
    candidates: list[dict] = field(default_factory=list)
    category: str = ""
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "source": self.source,
            "decision": self.decision,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "evidence": self.evidence,
            "candidates": self.candidates,
            "category": self.category,
            "tags": list(self.tags),
        }


# ── 후보 ─────────────────────────────────────────────────────────────────────


#: 프로젝트 이름의 「고객사」 쪽. 이름이 `<고객사> [<일감>]` 꼴이라 대괄호가 경계다.
_OWNER_PART = re.compile(r"^([^\[]+)")


def _project_index(db: Session) -> list[tuple[Project, set[str], set[str]]]:
    """프로젝트마다 (**식별 낱말**, 보조 낱말).

    이름이 「인천국제공항공사 [클라우드 인프라 고도화]」 꼴이라 가리키는 힘은 대괄호
    **앞**에 있다. 뒤쪽(일감)은 프로젝트마다 겹친다 — 「구축」·「고도화」·「클라우드」가
    여러 이름에 동시에 나온다.

    🔴 **식별 낱말은 「그 낱말을 쓰는 프로젝트가 하나뿐」인 것만이다.** 두 프로젝트가
    같이 쓰는 말은 어느 쪽도 안 가리키므로 판정을 만들 수 없고, 점수를 보태기만 한다.
    """
    rows = list(db.execute(sa.select(Project)).scalars().all())
    owned: list[tuple[Project, set[str], set[str]]] = []
    freq: dict[str, int] = {}
    for project in rows:
        owner = _tokens(_OWNER_PART.match(project.name or "").group(1)
                        if _OWNER_PART.match(project.name or "") else project.name)
        whole = set(_tokens(project.name))
        if project.code:
            whole.add(_norm(project.code))
        for token in whole:
            freq[token] = freq.get(token, 0) + 1
        owned.append((project, set(owner), whole))

    out: list[tuple[Project, set[str], set[str]]] = []
    for project, owner, whole in owned:
        # 그 낱말을 쓰는 프로젝트가 하나뿐일 때만 식별 낱말이다.
        identity = {t for t in whole if freq.get(t, 0) == 1}
        # 고객사 쪽이 먼저다. 일감 쪽에만 있는 유일 낱말도 식별에 넣되(예: 「NEXTHub」),
        # 고객사 쪽 낱말이 있으면 그쪽이 판정을 이끈다.
        if owner & identity:
            identity = (owner & identity) | {t for t in identity if len(t) >= 4}
        out.append((project, identity, whole - identity))
    return out


def _score(
    identity: set[str], support: set[str],
    title_tokens: list[str], body_tokens: list[str],
) -> tuple[int, list[str], bool]:
    """점수와 근거 낱말과 **제목이 이 프로젝트를 불렀는가**.

    긴 말에 가중치를 준다 — 「현대모비스」가 「관리」보다 그 프로젝트를 훨씬 강하게
    가리킨다. 식별 낱말은 보조 낱말의 세 배로 센다.

    🔴 세 번째 값이 「제목에 식별 낱말이 있는가」다. 본문이 아니다.
    제품 이름은 온갖 문서의 본문에 나온다(실측: `clovircm` 이 본문 46건). 그것을 근거로
    삼으면 「그 제품을 다룬다」가 「그 프로젝트의 문서다」가 되고, 국립암센터 문서가
    ClovirCM 프로젝트에 붙는다.
    """
    counts: dict[str, int] = {}
    for token in title_tokens + body_tokens:
        if token in identity or token in support:
            counts[token] = counts.get(token, 0) + 1
    total = 0
    for token, n in counts.items():
        weight = 3 if token in identity else 1
        total += min(3, n) * weight * (2 if len(token) >= 4 else 1)
    title_identity = any(t in identity for t in title_tokens)
    return (
        total,
        sorted(counts, key=lambda t: (t not in identity, -counts[t]))[:5],
        title_identity,
    )


def _body_text(db: Session, document: Document) -> str:
    if not document.current_version_id:
        return ""
    row = db.execute(
        sa.select(DocumentVersion.body_text).where(
            DocumentVersion.id == document.current_version_id
        )
    ).scalar_one_or_none()
    return (row or "")[:_BODY_WINDOW]


# ── 제안 ─────────────────────────────────────────────────────────────────────


def propose(db: Session, *, documents: list[Document], source: str) -> list[Proposal]:
    """문서마다 제안 한 줄. **아무것도 쓰지 않는다.**"""
    projects = _project_index(db)
    category_names = [
        row.name for row in db.execute(sa.select(DocumentCategory)).scalars().all()
    ]
    tag_names = [row.name for row in db.execute(sa.select(Tag)).scalars().all()]

    out: list[Proposal] = []
    for document in documents:
        title = document.title or ""
        body = _body_text(db, document)
        title_tokens = _tokens(title) * 3   # 제목은 본문보다 강한 신호다
        body_tokens = _tokens(body)

        scored = []
        for project, identity, support in projects:
            total, hits, title_identity = _score(
                identity, support, title_tokens, body_tokens
            )
            # 🔴 두 관문을 **함께** 지나야 후보다.
            #   1. 그 프로젝트 하나만 쓰는 낱말이 있을 것 (「변경」으로 KB국민카드에 붙던 자리)
            #   2. 그 낱말이 **제목에** 있을 것 (본문의 «clovircm» 으로 국립암센터가
            #      ClovirCM 에 붙던 자리)
            # 둘 다 실측이 만든 규칙이다.
            if title_identity and total >= _MIN_SCORE:
                scored.append((total, project, hits))
        scored.sort(key=lambda r: -r[0])

        proposal = Proposal(
            document_id=document.id, title=title, source=source,
            candidates=[
                {"project_id": p.id, "name": p.name, "score": s, "hits": h}
                for s, p, h in scored[:4]
            ],
        )
        if not scored:
            proposal.decision = DECISION_NONE
            proposal.evidence = "제목에 그 프로젝트만 쓰는 낱말이 안 나온다."
        elif len(scored) > 1 and (scored[0][0] - scored[1][0]) < _MIN_MARGIN:
            # 🔴 억지로 안 고른다. 거의 같은 후보 둘 중 하나를 고르는 것은 동전 던지기다.
            proposal.decision = DECISION_AMBIGUOUS
            proposal.evidence = (
                f"후보 둘의 점수가 비슷하다: "
                f"{scored[0][1].name}({scored[0][0]}) · {scored[1][1].name}({scored[1][0]})"
            )
        else:
            total, project, hits = scored[0]
            proposal.decision = DECISION_MATCHED
            proposal.project_id = project.id
            proposal.project_name = project.name
            proposal.evidence = f"«{'», «'.join(hits)}» 가 제목·본문에 나온다 (점수 {total})"

        proposal.category = _guess_category(title, body, category_names)
        proposal.tags = _guess_tags(title, body, tag_names)
        out.append(proposal)
    return out


def _guess_category(title: str, body: str, names: list[str]) -> str:
    """분류 하나. 못 정하면 **빈 값** — 적용기가 건너뛴다(기존 값을 안 지운다)."""
    title_tokens, body_tokens = _tokens(title) * 3, _tokens(body)
    best, best_score = "", 0
    for name in names:
        words = set(_tokens(name))
        score, _, _ = _score(words, set(), title_tokens, body_tokens)
        if score > best_score:
            best, best_score = name, score
    return best if best_score >= _MIN_SCORE else ""


def _guess_tags(title: str, body: str, names: list[str], *, limit: int = 6) -> list[str]:
    """태그 **여럿**. 하나만 고를 이유가 없다 — 한 문서가 여러 기술을 다룬다(12·16번)."""
    title_tokens, body_tokens = _tokens(title) * 2, _tokens(body)
    scored = []
    for name in names:
        # 태그는 **본문에 나오면 된다** — 「이 문서가 무엇을 다루는가」이지 「어느
        # 프로젝트의 것인가」가 아니라, 제목을 요구할 이유가 없다.
        score, _, _ = _score(set(_tokens(name)), set(), title_tokens, body_tokens)
        if score >= 4:
            scored.append((score, name))
    scored.sort(key=lambda r: (-r[0], r[1]))
    return [name for _, name in scored[:limit]]


# ── 파일 ─────────────────────────────────────────────────────────────────────


def write_proposals(path: str | Path, proposals: list[Proposal]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for proposal in proposals:
            handle.write(json.dumps(proposal.as_dict(), ensure_ascii=False) + "\n")
    return out


def read_proposals(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


# ── 적용 ─────────────────────────────────────────────────────────────────────


def is_rewritable(db: Session, document: Document) -> bool:
    """🔴 이 문서를 이관 결과로 고쳐도 되는가.

    **두 조건을 함께** 본다. `source_type` 만 보면 사람이 그 값을 바꾼 문서가 통과하고,
    `legacy_mapping` 만 보면 다리가 남아 있는 옛 문서가 통과한다. 자체 작성 문서는 둘 다
    아니므로 어느 쪽으로도 안 걸린다 — 제목이 같아도, 내용이 비슷해도(10번).
    """
    if document.source_type != SOURCE_MIGRATION:
        return False
    return db.execute(
        sa.select(LegacyMapping.id).where(
            LegacyMapping.target_type == T_DOCUMENT,
            LegacyMapping.target_id == document.id,
        )
    ).scalars().first() is not None


@dataclass
class ApplyResult:
    projects_set: int = 0
    projects_left_unassigned: int = 0
    categories_set: int = 0
    tags_set: int = 0
    refused_native: int = 0
    missing: int = 0

    def as_dict(self) -> dict:
        return {
            "projects_set": self.projects_set,
            "projects_left_unassigned": self.projects_left_unassigned,
            "categories_set": self.categories_set,
            "tags_set": self.tags_set,
            "refused_native": self.refused_native,
            "missing": self.missing,
        }


def apply(
    db: Session, rows: list[dict], *, actor, report=None, dry_run: bool = False
) -> ApplyResult:
    """검토한 파일을 실제로 쓴다. **파일에 없는 문서는 안 건드린다.**

    분류는 **비어 있을 때만** 채운다 — 사람이 이미 고른 분류를 추정으로 덮지 않는다.
    태그는 **합집합**이다: 원래 있던 태그를 지우지 않는다.
    """
    from app.migration.report import SEVERITY_BLOCKING, SEVERITY_NOTE

    result = ApplyResult()
    org_id = getattr(actor, "org_id", None)
    for row in rows:
        document = db.get(Document, row.get("document_id") or "")
        if document is None:
            result.missing += 1
            continue
        if not is_rewritable(db, document):
            # 🔴 자체 작성 문서다. 파일이 무엇을 적었든 안 고친다.
            result.refused_native += 1
            if report is not None:
                report.finding(
                    SEVERITY_BLOCKING, "classify_refused_native_document", "documents",
                    f"자체 작성 문서라 분류를 안 바꿨습니다: {document.title}",
                    ref=document.id,
                )
            continue

        decision = row.get("decision") or DECISION_NONE
        project_id = row.get("project_id")
        if decision in (DECISION_MATCHED, DECISION_MANUAL) and project_id:
            if not dry_run:
                _move_to_project(db, actor, document, project_id)
            result.projects_set += 1
        else:
            # 판단이 안 서면 **비운 채로 둔다.** 억지로 붙이지 않는 것이 요구다.
            result.projects_left_unassigned += 1

        category = (row.get("category") or "").strip()
        if category and not document.category_id:
            if not dry_run:
                document.category_id = _category_id(db, org_id, category)
            result.categories_set += 1

        wanted = [t for t in (row.get("tags") or []) if t and t.strip()]
        if wanted:
            if not dry_run:
                have = [t.name for t in doc_tags.of_document(db, document.id)]
                merged = list(dict.fromkeys([*have, *wanted]))[:doc_tags.TAG_MAX_PER_DOCUMENT]
                doc_tags.set_for_document(db, document, merged)
            result.tags_set += 1

    if report is not None and result.projects_left_unassigned:
        report.finding(
            SEVERITY_NOTE, "classify_left_unassigned", "documents",
            f"프로젝트를 판단하지 못한 문서 {result.projects_left_unassigned}건은 "
            "미지정으로 두었습니다.",
        )
    if not dry_run:
        db.flush()
    return result


def _move_to_project(db: Session, actor, document: Document, project_id: str) -> None:
    """문서를 그 프로젝트의 공간으로 옮긴다.

    프로젝트 배정은 **공간 이동**이라 권한 경계가 바뀐다. 옛 폴더 참조는 버린다(다른
    공간의 폴더를 가리키게 둘 수 없다). 낙관적 잠금 판도 올린다 — 열어 둔 화면이 있으면
    그 저장이 충돌로 막혀야 한다.
    """
    space = knowledge_service.resolve_or_create_project_space(db, actor, project_id)
    if space.id == document.space_id:
        return
    document.space_id = space.id
    document.folder_id = None
    document.version += 1


def _category_id(db: Session, org_id: str | None, name: str) -> str | None:
    """이름으로 분류를 찾거나 만든다. 필요하면 새로 만들어도 된다는 것이 요구다(12·16번)."""
    slug = doc_tags.slugify(name)
    row = db.execute(
        sa.select(DocumentCategory).where(
            DocumentCategory.org_id.is_(None) if org_id is None
            else DocumentCategory.org_id == org_id,
            DocumentCategory.slug == slug,
        )
    ).scalars().first()
    if row is not None:
        return row.id
    created = doc_categories.create(db, org_id, name)
    return created.id


def migrated_documents(db: Session, *, source: str | None = None) -> list[Document]:
    """이관·Import 로 들어온 문서만. **자체 작성 문서는 후보에도 안 든다.**"""
    stmt = (
        sa.select(Document)
        .join(LegacyMapping, sa.and_(
            LegacyMapping.target_type == T_DOCUMENT,
            LegacyMapping.target_id == Document.id,
        ))
        .where(Document.source_type == SOURCE_MIGRATION)
    )
    if source:
        stmt = stmt.where(LegacyMapping.legacy_source == source)
    return list(db.execute(stmt.order_by(Document.created_at)).scalars().unique().all())


def unassigned_space_ids(db: Session) -> list[str]:
    """프로젝트 소유가 아닌 공간들. 적용 전후를 비교하는 자리가 쓴다."""
    return list(db.execute(
        sa.select(KnowledgeSpace.id).where(KnowledgeSpace.owner_kind != "project")
    ).scalars().all())
