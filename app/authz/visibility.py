"""`effective_visibility_clause` — **무엇이 보이는가**를 정하는 단 하나의 자리 (D-193 · D-194).

목록·상세·Search·(S10 부터) AI Retrieval 이 전부 여기를 지난다. 「같은 규칙을 따른다」는
주석은 증거가 아니므로 `scripts/check_visibility_single_source.py` 가 코드로 확인한다.

## 규칙은 하나인데 답해야 할 모양이 둘이다

    목록 · Search   →  SQL 절 하나 (상한 앞에 걸려야 한다, Z6)
    상세 · 행 판정  →  파이썬 불리언 하나

두 벌로 적으면 갈라진다 — 그리고 갈라진 순간 「목록에는 없는데 id 로는 열리는」 상태가 된다.
그래서 규칙마다 두 표현을 **한 객체(`_Rule`)에 나란히** 만들고, 두 렌더러는 같은 규칙 목록을
서로 다른 방식으로 접기만 한다. 같은 답을 내는지는
`tests/security/test_visibility_two_renderers_agree.py` 가 실제 행으로 확인한다.

## 더하기만 한다, 그리고 모르면 닫는다 (D-193)

    유효 가시성 = 소속 ∪ Project Member ∪ 직접 부여

`or_` 로 묶이는 이 세 갈래가 전부다. 좁히는 Override 는 없다. 어느 갈래에도 안 걸리는 행
(`owner_kind = 'unset'`)은 그래서 **전역 관리자만** 본다 — 추측해서 열지 않는다.

## 유일한 축소 원시연산은 `confidential` 하나다

    소유자 + 명시 부여자 + `*_ADMIN` 보유자만

이 한 문장이 전부이고, 자원 종류마다 다시 해석하지 않는다. 다만 **검색은 예외를 하나도
두지 않는다**(`CONFIDENTIAL_NOBODY`) — 색인은 범위가 없는 전역 저장소라 예외를 하나 열면
그것이 인덱스 안 ACL 의 시작이 된다. 그 판단은 원래 `app/search/scoping.py` 에 있었고,
여기로 옮기면서 **자원 명세의 한 칸**이 되었다. 두 자원이 왜 다른지가 이제 한 표에 보인다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.authz import permissions as perms
from app.authz.models import GRANTEE_USER, ResourceGrant
from app.authz.service import effective_permissions, principal_grantee_pairs
from app.core.models_base import NAMES_SEP
from app.core.ownership import (
    OWNER_DEPARTMENT,
    OWNER_ORGANIZATION,
    OWNER_PROJECT,
)
from app.core.scope import MATCH_NOTHING, Scope

__all__ = [
    "RESOURCE_PROJECT",
    "RESOURCE_DOCUMENT",
    "RESOURCE_SEARCH",
    "ALL_RESOURCE_TYPES",
    "VisibilityContext",
    "visibility_context",
    "context_for_user",
    "effective_visibility_clause",
    "is_visible",
    "annotate_rows",
    "visible_project_ids",
    "users_who_can_view_project",
    "scope_only_context",
]

# ── 자원 종류 ────────────────────────────────────────────────────────────────
# 값은 `app/search/models.py` 의 `KIND_*` 와 같은 어휘를 쓴다 — 색인 행이 원본을 가리킬 때
# 그 문자열이 그대로 `resource_grants.resource_type` 이 되어야 부여가 두 곳에서 같은 자원을
# 뜻한다.
RESOURCE_PROJECT = "project"
RESOURCE_DOCUMENT = "document"
RESOURCE_SEARCH = "search"

ALL_RESOURCE_TYPES = frozenset({RESOURCE_PROJECT, RESOURCE_DOCUMENT, RESOURCE_SEARCH})

# ── `confidential` 을 어떻게 해석하는가 ──────────────────────────────────────
CONFIDENTIAL_NONE = "none"              # 이 자원에는 축소 플래그가 없다
CONFIDENTIAL_OWNER_ADMIN = "owner_admin"  # 소유자 + 명시 부여자 + *_ADMIN
CONFIDENTIAL_NOBODY = "nobody"          # 예외 없음 (색인)

CONFIDENTIAL_MODE: dict[str, str] = {
    RESOURCE_PROJECT: CONFIDENTIAL_NONE,
    RESOURCE_DOCUMENT: CONFIDENTIAL_OWNER_ADMIN,
    RESOURCE_SEARCH: CONFIDENTIAL_NOBODY,
}

# `confidential` 을 여는 `*_ADMIN`. 없으면 아무 권한도 그것을 열지 못한다.
ADMIN_PERMISSION: dict[str, str | None] = {
    RESOURCE_PROJECT: perms.PROJECT_ADMIN,
    RESOURCE_DOCUMENT: perms.DOCUMENT_ADMIN,
    RESOURCE_SEARCH: None,
}


@dataclass(frozen=True)
class _Rule:
    """가시성 갈래 하나 — SQL 과 행 판정을 **함께** 들고 있다."""

    sql: Any
    row: Callable[[Any], bool]


@dataclass(frozen=True)
class _Plan:
    """한 자원 종류에 대한 판정 계획.

    `unrestricted` 는 「조건 없음」이다. `sa.true()` 로 돌려주지 않는 이유는
    `app/core/scope.py::scope_filter` 와 같다 — 조건을 빼먹은 코드와 조건이 항상 참인
    코드가 눈으로 구별되지 않게 된다.
    """

    widen: tuple[_Rule, ...] = ()
    narrow: tuple[_Rule, ...] = ()
    unrestricted: bool = False


@dataclass(frozen=True)
class VisibilityContext:
    """판정 재료 한 벌. **요청당 한 번** 만든다.

    목록 한 페이지가 행마다 판정을 부르는데, 재료를 그때마다 다시 읽으면 그대로 N+1 이다
    (FN-41 이 그 모양이었다).
    """

    principal: Any
    scope: Scope
    permissions: frozenset[str]
    grantee_pairs: tuple[tuple[str, str], ...]
    member_project_ids: frozenset[str]
    # 이 주체가 명시로 받은 자원 전부 — `(자원 종류, 자원 id)` 집합.
    #
    # **행 판정이 행마다 묻지 않게 하려고 한 번에 싣는다.** 한 사람이 명시로 받는 자원은
    # 「누군가 나에게 열어 준 것」이라 수가 작다(범위·부서로 보이는 것은 여기 안 들어온다).
    # 목록이 행마다 물으면 그대로 N+1 이고, 그것이 FN-41 의 모양이다.
    granted: frozenset[tuple[str, str]] = frozenset()
    my_notion_id: str | None = None
    display_name: str = ""
    # 프로젝트 가시성의 파이썬 답. `None` 이면 제한 없음(전역).
    visible_projects: frozenset[str] | None = field(default=None)


def visibility_context(
    db: Session, principal, *, scope: Scope | None = None, user=None
) -> VisibilityContext:
    """`principal` 하나에서 판정 재료를 모은다.

    `scope` 를 주면 **그것으로 더 좁힌다**(넓히지 못한다) — 목록 화면의 부서 필터가 그
    인자를 쓴다. 부르는 쪽이 이미 그 사람의 조회 범위 안에서 검증한 값만 넘긴다.
    """
    from app.projects.models import ProjectMember

    default_scope = scope is None
    scope = scope if scope is not None else principal.visibility
    if default_scope:
        cached = getattr(principal, "_authz_visibility_ctx", None)
        if cached is not None:
            return cached

    member_ids = frozenset(
        db.execute(
            select(ProjectMember.project_id).where(
                ProjectMember.user_id == principal.user_id
            )
        ).scalars().all()
    )

    permissions = _permissions_of(db, principal, user)
    notion_id, display_name = _identity_of(db, principal, user)
    pairs = principal_grantee_pairs(db, principal)

    ctx = VisibilityContext(
        principal=principal,
        scope=scope,
        permissions=permissions,
        grantee_pairs=pairs,
        member_project_ids=member_ids,
        granted=_granted_to(db, pairs),
        my_notion_id=notion_id,
        display_name=display_name,
    )
    # 프로젝트 집합은 문서·티켓의 소속 갈래가 매행 물어보는 값이라 여기서 한 번에 굳힌다.
    projects = _resolve_visible_projects(db, ctx)
    ctx = VisibilityContext(**{**ctx.__dict__, "visible_projects": projects})
    if default_scope:
        try:
            object.__setattr__(principal, "_authz_visibility_ctx", ctx)
        except AttributeError:  # pragma: no cover
            pass
    return ctx


def context_for_user(db: Session, user, *, scope: Scope | None = None) -> VisibilityContext:
    """`Principal` 이 아직 없는 자리에서 쓰는 입구.

    서비스 계층 상당수가 `user` 만 들고 다닌다(라우터가 `get_principal` 을 안 쓰는 경로).
    거기서 `Principal` 을 새로 만드는 것보다 이 한 줄이 정직하다 — 판정에 쓰이는 값은
    똑같고, 부서 트리도 한 번만 읽는다.
    """
    from app.core.org_tree import DeptTree
    from app.core.scope import principal_from_user

    principal = principal_from_user(db, user, DeptTree.load(db))
    return visibility_context(db, principal, scope=scope, user=user)


def _granted_to(db: Session, pairs: tuple[tuple[str, str], ...]) -> frozenset[tuple[str, str]]:
    """이 주체가 명시로 받은 자원 전부. 질의 **한 번**이다."""
    if not pairs:
        return frozenset()
    rows = db.execute(
        select(ResourceGrant.resource_type, ResourceGrant.resource_id).where(
            _grantee_match_sql(pairs)
        )
    ).all()
    return frozenset((t, i) for t, i in rows)


def _permissions_of(db: Session, principal, user) -> frozenset[str]:
    if user is not None:
        return effective_permissions(db, user)
    from app.users.models import User

    row = db.get(User, principal.user_id)
    return effective_permissions(db, row) if row is not None else frozenset()


def _identity_of(db: Session, principal, user) -> tuple[str | None, str]:
    """`confidential` 의 「소유자」 판정에 필요한 두 값.

    문서의 작성자 판정이 Notion id 우선, 없으면 표시 이름 폴백이라 둘 다 필요하다
    (`app/team_docs/service.py::_is_doc_author` 의 규칙 그대로다).
    """
    from app.tickets.service import my_notion_id as _my_notion_id
    from app.users.models import User

    row = user if user is not None else db.get(User, principal.user_id)
    if row is None:
        return None, ""
    return _my_notion_id(db, row), (getattr(row, "display_name", "") or "").strip()


# ── 공통 갈래 ────────────────────────────────────────────────────────────────

def _grant_rule(
    ctx: VisibilityContext, *, resource_type_col, resource_id_col, resource_type: str
) -> _Rule:
    """직접 부여 갈래 — D-193 의 마지막 항.

    `resource_type_col` 이 컬럼이면 색인처럼 **행마다 자원 종류가 다른** 표도 같은 규칙을
    쓴다. 문자열이면 그 종류로 고정한다.

    행 판정은 `ctx.granted` 집합 조회다 — **질의가 없다.** 목록이 행마다 부여를 물으면
    그대로 N+1 이고, 그 함정은 이 저장소가 문서 목록에서 이미 한 번 밟았다(FN-41).
    """
    if not ctx.granted:
        # 받은 부여가 없으면 이 갈래는 아무것도 열지 않는다. `false()` 는 PG 에서 `false` 로
        # 컴파일돼 조건을 빼먹은 코드와 눈으로 구별된다(`app/core/scope.py::MATCH_NOTHING`).
        return _Rule(sql=false(), row=lambda obj: False)

    # SQL 은 부여 **자격**(누구로서 받는가)이 있어야 쓸 수 있다. 역방향 판정
    # (`users_who_can_view_project`)은 사람마다 자격이 다르므로 자격 없이 `granted` 집합만
    # 들고 오는데, 그쪽은 행 판정만 쓰므로 SQL 은 닫아 둔다.
    exists = (
        select(ResourceGrant.id)
        .where(
            ResourceGrant.resource_type == resource_type_col,
            ResourceGrant.resource_id == resource_id_col,
            _grantee_match_sql(ctx.grantee_pairs),
        )
        .exists()
    ) if ctx.grantee_pairs else false()

    def row(obj, rtype=resource_type, granted=ctx.granted) -> bool:
        key = _grant_key(rtype, obj)
        return key is not None and key in granted

    return _Rule(sql=exists, row=row)


def _grantee_match_sql(pairs: tuple[tuple[str, str], ...]):
    return or_(
        *[
            and_(ResourceGrant.grantee_kind == kind, ResourceGrant.grantee_id == gid)
            for kind, gid in pairs
        ]
    )


# 자원 종류별 「그 행의 id 는 어느 칸에 있는가」. 부여 표가 가리키는 키다.
RESOURCE_ID_ATTR: dict[str, str] = {
    RESOURCE_PROJECT: "id",
    RESOURCE_DOCUMENT: "notion_page_id",
    RESOURCE_SEARCH: "ref_id",
}


def _grant_key(resource_type: str, row) -> tuple[str, str] | None:
    """이 행이 부여 표에서 어떤 `(종류, id)` 로 불리는가.

    색인 행은 **자기가 가리키는 원본**의 종류를 쓴다(`kind`) — 그래야 문서에 준 부여가
    검색에서도 같은 자원을 뜻한다.
    """
    attr = RESOURCE_ID_ATTR.get(resource_type)
    if attr is None:
        return None
    rid = getattr(row, attr, None)
    if not rid:
        return None
    kind = getattr(row, "kind", None) if resource_type == RESOURCE_SEARCH else resource_type
    return (str(kind), str(rid)) if kind else None


def annotate_rows(db: Session, ctx: VisibilityContext, resource_type: str, rows) -> None:
    """행 판정이 필요로 하는데 **행 자신도 컨텍스트도 모르는** 사실을 실어 준다.

    지금은 하나뿐이다 — 색인 행의 `_authz_restricted`(원본 문서가 열람 제한인가). 색인 행에는
    그 값이 없어서 원본을 봐야 하고, 그래서 페이지 전체에 대해 **질의 한 번**으로 붙인다.

    부여 여부는 여기서 다루지 않는다. `ctx.granted` 가 요청당 한 번 통째로 실려 있어
    행 판정이 집합 조회로 끝난다 — 행마다 물으면 그대로 N+1 이다(FN-41).
    """
    rows = [r for r in rows if r is not None]
    if not rows or resource_type != RESOURCE_SEARCH:
        return
    _annotate_search_restricted(db, rows)


def _annotate_search_restricted(db: Session, rows) -> None:
    from app.search.models import KIND_DOCUMENT
    from app.team_docs.models import DocumentCache

    refs = {
        str(getattr(r, "ref_id"))
        for r in rows
        if getattr(r, "kind", None) == KIND_DOCUMENT and getattr(r, "ref_id", None)
    }
    restricted: frozenset[str] = frozenset()
    if refs:
        restricted = frozenset(
            db.execute(
                select(DocumentCache.notion_page_id).where(
                    DocumentCache.notion_page_id.in_(tuple(sorted(refs))),
                    DocumentCache.restricted.is_(True),
                )
            ).scalars().all()
        )
    for r in rows:
        hit = (
            getattr(r, "kind", None) == KIND_DOCUMENT
            and str(getattr(r, "ref_id", "")) in restricted
        )
        object.__setattr__(r, "_authz_restricted", hit)


# ── 자원별 계획 ──────────────────────────────────────────────────────────────

def _project_plan(ctx: VisibilityContext) -> _Plan:
    """프로젝트 — 소속(부서/조직) ∪ 프로젝트 멤버 ∪ 직접 부여.

    `dept_id IS NULL` 인 프로젝트는 **조직 공통**이다(`app/core/ownership.py::for_project`).
    부서 범위에서도 보여야 한다 — 예전에 `dept_id IN (...)` 이 NULL 을 못 잡아 조직 공통
    프로젝트가 부서 사용자에게 통째로 사라진 적이 있다.

    **프로젝트 멤버 갈래가 S5 에서 새로 생겼다** (D-193 의 `Project Member` 항). 부서가
    달라도 그 프로젝트에 참여하면 보인다 — 참여시켜 놓고 안 보이는 상태는 설명할 수 없다.
    """
    from app.projects.models import Project

    if ctx.scope.is_global:
        return _Plan(unrestricted=True)

    rules: list[_Rule] = []
    scope = ctx.scope

    if scope.is_org and scope.org_id:
        rules.append(_Rule(
            sql=Project.org_id == scope.org_id,
            row=lambda p, org=scope.org_id: getattr(p, "org_id", None) == org,
        ))
    elif scope.is_dept and scope.dept_ids:
        dept_ids = frozenset(scope.dept_ids)
        rules.append(_Rule(
            sql=Project.dept_id.in_(tuple(sorted(dept_ids))),
            row=lambda p, ids=dept_ids: getattr(p, "dept_id", None) in ids,
        ))
        if scope.org_id:
            rules.append(_Rule(
                sql=and_(Project.dept_id.is_(None), Project.org_id == scope.org_id),
                row=lambda p, org=scope.org_id: (
                    getattr(p, "dept_id", None) is None and getattr(p, "org_id", None) == org
                ),
            ))

    if ctx.member_project_ids:
        member_ids = ctx.member_project_ids
        rules.append(_Rule(
            sql=Project.id.in_(tuple(sorted(member_ids))),
            row=lambda p, ids=member_ids: getattr(p, "id", None) in ids,
        ))

    rules.append(_grant_rule(
        ctx, resource_type_col=RESOURCE_PROJECT, resource_id_col=Project.id,
        resource_type=RESOURCE_PROJECT,
    ))
    return _Plan(widen=tuple(rules))


def _stored_ownership_rules(
    ctx: VisibilityContext, *, kind_col, org_col, dept_col, project_col
) -> list[_Rule]:
    """`owner_kind` + 세 컬럼을 저장하는 표(문서·색인)의 소속 갈래들.

    `unset` 은 어느 갈래에도 안 걸린다 — 그것이 fail-closed 가 사는 자리다.
    """
    scope = ctx.scope
    rules: list[_Rule] = []

    if scope.org_id:
        org_id = scope.org_id
        rules.append(_Rule(
            sql=and_(kind_col == OWNER_ORGANIZATION, org_col == org_id),
            row=lambda o, oid=org_id, kc=kind_col, oc=org_col: (
                _row_value(o, kc) == OWNER_ORGANIZATION and _row_value(o, oc) == oid
            ),
        ))
    if scope.is_org:
        if scope.org_id:
            org_id = scope.org_id
            rules.append(_Rule(
                sql=and_(kind_col == OWNER_DEPARTMENT, org_col == org_id),
                row=lambda o, oid=org_id, kc=kind_col, oc=org_col: (
                    _row_value(o, kc) == OWNER_DEPARTMENT and _row_value(o, oc) == oid
                ),
            ))
    elif scope.dept_ids:
        dept_ids = frozenset(scope.dept_ids)
        rules.append(_Rule(
            sql=and_(kind_col == OWNER_DEPARTMENT, dept_col.in_(tuple(sorted(dept_ids)))),
            row=lambda o, ids=dept_ids, kc=kind_col, col=dept_col: (
                _row_value(o, kc) == OWNER_DEPARTMENT and _row_value(o, col) in ids
            ),
        ))

    projects = ctx.visible_projects
    rules.append(_Rule(
        sql=and_(kind_col == OWNER_PROJECT, project_col.in_(_project_id_subquery(ctx))),
        row=lambda o, ids=projects, kc=kind_col, col=project_col: (
            _row_value(o, kc) == OWNER_PROJECT
            and (ids is None or _row_value(o, col) in ids)
        ),
    ))
    return rules


def _row_value(obj, column):
    """SQLAlchemy 컬럼이 가리키는 값을 **행 객체**에서 꺼낸다.

    컬럼 이름을 문자열로 한 번 더 적지 않기 위해서다 — 두 벌로 적으면 한쪽만 고쳐진다.
    """
    return getattr(obj, column.key, None)


def _document_plan(ctx: VisibilityContext) -> _Plan:
    from app.team_docs.models import DocumentCache

    if ctx.scope.is_global:
        widen: tuple[_Rule, ...] = ()
        unrestricted_widen = True
    else:
        unrestricted_widen = False
        rules = _stored_ownership_rules(
            ctx,
            kind_col=DocumentCache.owner_kind,
            org_col=DocumentCache.org_id,
            dept_col=DocumentCache.owner_dept_id,
            project_col=DocumentCache.owner_project_id,
        )
        rules.append(_grant_rule(
            ctx,
            resource_type_col=RESOURCE_DOCUMENT,
            resource_id_col=DocumentCache.notion_page_id,
            resource_type=RESOURCE_DOCUMENT,
        ))
        widen = tuple(rules)

    narrow = (_confidential_rule_for_document(ctx),)
    if unrestricted_widen:
        # 전역 조회라도 축소 플래그는 그대로 적용된다 — `confidential` 은 범위가 아니라
        # 자원 자신의 성질이다. 다만 전역 관리자는 `*_ADMIN` 을 갖고 있어 대개 통과한다.
        return _Plan(widen=(_Rule(sql=None, row=lambda obj: True),), narrow=narrow)
    return _Plan(widen=widen, narrow=narrow)


def _confidential_rule_for_document(ctx: VisibilityContext) -> _Rule:
    """`confidential` = 소유자 + 명시 부여자 + `*_ADMIN` 보유자만 (D-193).

    문서에서 「소유자」는 작성자다 — id 가 있으면 Notion id, 없으면 표시 이름 폴백이고
    그 규칙은 `app/team_docs/service.py::_is_doc_author` 가 쓰던 것 그대로다.
    """
    from app.team_docs.models import DocumentCache

    admin_key = ADMIN_PERMISSION[RESOURCE_DOCUMENT]
    if admin_key and admin_key in ctx.permissions:
        return _Rule(sql=None, row=lambda obj: True)

    # 명시 부여는 축소 절도 연다 — 그것이 D-193 이 정한 세 예외 중 둘째다.
    grant = _grant_rule(
        ctx, resource_type_col=RESOURCE_DOCUMENT, resource_id_col=DocumentCache.notion_page_id,
        resource_type=RESOURCE_DOCUMENT,
    )
    open_sql = or_(
        DocumentCache.restricted.is_(False),
        _document_author_sql(ctx),
    )

    def row(obj) -> bool:
        if not getattr(obj, "restricted", False):
            return True
        if grant.row(obj):
            return True
        return _document_author_row(ctx, obj)

    return _Rule(sql=or_(open_sql, grant.sql), row=row)


def _has_author_ids_sql():
    """`author_notion_ids` 에 **빈 것 말고** 값이 있는가.

    구분자를 전부 지우고 남는 것이 있는지로 판단한다 — `split_names` 가 공백 토큰을
    버리는 규칙과 같은 답을 낸다(`\\x1f\\x1f` 는 '없음'이다).
    """
    from app.team_docs.models import DocumentCache

    stripped = func.btrim(func.replace(
        func.coalesce(DocumentCache.author_notion_ids, ""), NAMES_SEP, ""
    ))
    return stripped != ""


def _document_author_sql(ctx: VisibilityContext):
    from app.team_docs.models import DocumentCache

    by_id = (
        DocumentCache.author_notion_ids.contains(NAMES_SEP + ctx.my_notion_id + NAMES_SEP)
        if ctx.my_notion_id
        else false()
    )
    if ctx.display_name:
        by_name = or_(
            DocumentCache.author_names.contains(NAMES_SEP + ctx.display_name + NAMES_SEP),
            func.btrim(func.coalesce(DocumentCache.owner, "")) == ctx.display_name,
        )
    else:
        by_name = false()
    has_ids = _has_author_ids_sql()
    return or_(and_(has_ids, by_id), and_(~has_ids, by_name))


def _document_author_row(ctx: VisibilityContext, doc) -> bool:
    from app.core.models_base import split_names

    author_ids = [a for a in split_names(getattr(doc, "author_notion_ids", "") or "") if a]
    if author_ids:
        return bool(ctx.my_notion_id) and ctx.my_notion_id in author_ids
    name = ctx.display_name
    authors = {a.strip() for a in split_names(getattr(doc, "author_names", "") or "")}
    return bool(name) and (
        name in authors or name == (getattr(doc, "owner", "") or "").strip()
    )


def _search_plan(ctx: VisibilityContext) -> _Plan:
    """색인 행 — 소속은 문서와 같은 규칙, 축소는 **예외 없음**이다.

    색인은 범위가 없는 전역 저장소다. 여기에 「작성자와 운영자는 예외」를 하나 열면 그
    예외가 인덱스 안 ACL 의 시작이 된다. 기능을 잃지도 않는다 — 그 사람들은 문서 목록에서
    그대로 보고 연다.
    """
    from app.search.models import KIND_DOCUMENT, SearchDocument
    from app.team_docs.models import DocumentCache

    narrow_sql = or_(
        SearchDocument.kind != KIND_DOCUMENT,
        SearchDocument.ref_id.not_in(
            select(DocumentCache.notion_page_id).where(DocumentCache.restricted.is_(True))
        ),
    )

    def narrow_row(obj) -> bool:
        # 행 판정은 색인 행 자체에 제한 여부가 없어 원본을 봐야 한다. 목록 경로는 SQL 을
        # 쓰므로 이 갈래는 두 렌더러 대조 시험에서만 불린다.
        return not bool(getattr(obj, "_authz_restricted", False))

    narrow = (_Rule(sql=narrow_sql, row=narrow_row),)

    if ctx.scope.is_global:
        return _Plan(widen=(_Rule(sql=None, row=lambda obj: True),), narrow=narrow)

    rules = _stored_ownership_rules(
        ctx,
        kind_col=SearchDocument.owner_kind,
        org_col=SearchDocument.org_id,
        dept_col=SearchDocument.owner_dept_id,
        project_col=SearchDocument.owner_project_id,
    )
    rules.append(_grant_rule(
        ctx, resource_type_col=SearchDocument.kind, resource_id_col=SearchDocument.ref_id,
        resource_type=RESOURCE_SEARCH,
    ))
    return _Plan(widen=tuple(rules), narrow=narrow)


_PLANS: dict[str, Callable[[VisibilityContext], _Plan]] = {
    RESOURCE_PROJECT: _project_plan,
    RESOURCE_DOCUMENT: _document_plan,
    RESOURCE_SEARCH: _search_plan,
}


def _plan(ctx: VisibilityContext, resource_type: str) -> _Plan:
    builder = _PLANS.get(resource_type)
    if builder is None:
        # 등록되지 않은 자원은 **아무것도 보이지 않는다.** 새 자원을 등록하지 않은 채
        # 목록을 열면 빈 화면이 나오고, 그건 조용히 전량이 열리는 것보다 낫다.
        return _Plan(widen=())
    return builder(ctx)


# ── 두 렌더러 ────────────────────────────────────────────────────────────────

def effective_visibility_clause(ctx: VisibilityContext, resource_type: str):
    """이 주체가 볼 수 있는 행의 조건. **전역이면 `None`**(= 조건 없음).

    ⚠️ 이 절은 **후보 상한(`LIMIT`) 앞에** 걸려야 한다. 범위 밖 행이 상한을 채우면 내 범위
    결과가 한 건도 안 남는데, 오류가 아니라서 아무도 신고하지 않는다(Z6 · D-202).
    """
    plan = _plan(ctx, resource_type)
    if plan.unrestricted:
        return None
    widen_sql = [r.sql for r in plan.widen if r.sql is not None]
    narrow_sql = [r.sql for r in plan.narrow if r.sql is not None]

    if plan.widen and not widen_sql:
        # 전부 「조건 없음」인 갈래(전역 조회) — 넓히는 쪽은 항상 참이다.
        base = None
    elif not widen_sql:
        base = MATCH_NOTHING
    else:
        base = or_(*widen_sql)

    if not narrow_sql:
        return base
    if base is None:
        return and_(*narrow_sql)
    return and_(base, *narrow_sql)


def is_visible(db: Session, ctx: VisibilityContext, resource_type: str, row) -> bool:
    """행 하나 판정. 위 SQL 절과 **같은 규칙 목록**을 접는다.

    색인 행만 원본을 한 번 봐야 한다(`_authz_restricted`). 목록은 페이지 전체에 대해
    `annotate_rows` 를 먼저 부르므로 그 경로에서는 추가 질의가 생기지 않는다.
    문서·프로젝트 판정에는 **질의가 아예 없다.**
    """
    if resource_type == RESOURCE_SEARCH and not hasattr(row, "_authz_restricted"):
        annotate_rows(db, ctx, resource_type, [row])
    plan = _plan(ctx, resource_type)
    if plan.unrestricted:
        return True
    if not any(rule.row(row) for rule in plan.widen):
        return False
    return all(rule.row(row) for rule in plan.narrow)


# ── 프로젝트 집합 ────────────────────────────────────────────────────────────

def _project_id_subquery(ctx: VisibilityContext):
    """범위 안 프로젝트 id 를 고르는 **서브쿼리**.

    파이썬으로 id 를 먼저 뽑아 오지 않는다 — 프로젝트가 수백 개가 되면 그 목록이 그대로
    SQL 파라미터가 되고, 무엇보다 목록 질의가 **페이지를 자르기 전에** 걸려야 하는데
    파이썬 왕복이 끼면 그 순서를 지키기 어렵다.
    """
    from app.projects.models import Project

    stmt = select(Project.id)
    clause = effective_visibility_clause(ctx, RESOURCE_PROJECT)
    return stmt if clause is None else stmt.where(clause)


def visible_project_ids(ctx: VisibilityContext):
    """공개 이름. 티켓·문서가 `IN (...)` 로 쓴다."""
    return _project_id_subquery(ctx)


def _resolve_visible_projects(db: Session, ctx: VisibilityContext) -> frozenset[str] | None:
    if ctx.scope.is_global:
        return None
    return frozenset(db.execute(_project_id_subquery(ctx)).scalars().all())


# ── 역방향 판정 ──────────────────────────────────────────────────────────────

def scope_only_context(
    scope: Scope,
    *,
    member_project_ids: frozenset[str] = frozenset(),
    granted: frozenset[tuple[str, str]] = frozenset(),
) -> VisibilityContext:
    """질의 없이 만드는 판정 재료.

    「이 자원을 볼 수 있는 **사람이 누구인가**」를 거꾸로 묻는 자리가 쓴다. 사람마다
    `visibility_context` 를 만들면 요청이 사람 수만큼 늘어나는데, 범위 계산은 부서 트리만
    있으면 질의 없이 끝난다.
    """
    return VisibilityContext(
        principal=None,
        scope=scope,
        permissions=frozenset(),
        grantee_pairs=(),
        member_project_ids=member_project_ids,
        granted=granted,
        visible_projects=None if scope.is_global else frozenset(),
    )


def users_who_can_view_project(db: Session, users, project, *, tree=None) -> list:
    """이 프로젝트를 **볼 수 있는** 사람만 남긴다. 프로젝트가 없으면 빈 목록(fail-closed).

    앞의 `is_visible` 과 **같은 규칙 목록**(`_project_plan`)을 사람마다 접는다 — 여기서
    조건을 다시 적으면 「담당자 후보로는 떴는데 그 사람은 그 프로젝트를 못 본다」가 된다.
    질의는 사람 수와 무관하게 셋이다: 부서 트리 한 번, 멤버 한 번, 부여 한 번.
    """
    from app.core.org_tree import DeptTree
    from app.core.scope import visibility_scope
    from app.projects.models import ProjectMember

    if project is None:
        return []
    tree = tree if tree is not None else DeptTree.load(db)
    project_id = getattr(project, "id", None)

    members = frozenset(
        db.execute(
            select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
        ).scalars().all()
    )
    granted_users = frozenset(
        db.execute(
            select(ResourceGrant.grantee_id).where(
                ResourceGrant.resource_type == RESOURCE_PROJECT,
                ResourceGrant.resource_id == project_id,
                ResourceGrant.grantee_kind == GRANTEE_USER,
            )
        ).scalars().all()
    )

    mine = frozenset({project_id}) if project_id else frozenset()
    this_grant = frozenset({(RESOURCE_PROJECT, str(project_id))}) if project_id else frozenset()
    out = []
    for user in users:
        ctx = scope_only_context(
            visibility_scope(db, user, tree),
            member_project_ids=mine if user.id in members else frozenset(),
            granted=this_grant if user.id in granted_users else frozenset(),
        )
        plan = _project_plan(ctx)
        if plan.unrestricted or any(rule.row(project) for rule in plan.widen):
            out.append(user)
    return out
